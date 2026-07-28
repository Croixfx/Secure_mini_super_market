"""
sales/tests.py

Each test proves one property that would otherwise just be a claim in a
comment:
- price tampering from the client is ignored
- a multi-item cart with one out-of-stock line rolls back entirely
- the same idempotency key never creates two sales
- a cashier can only sell for their own branch
"""
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role
from branches.models import Branch
from inventory import services
from inventory.models import Category, Product, StockMovement

from .models import Sale

User = get_user_model()


class CheckoutTests(APITestCase):
    def setUp(self):
        # ScopedRateThrottle's counters live in the default cache, which
        # persists for the whole test run (not per-test) — clear it so the
        # 5/min login throttle from an earlier test doesn't 429 this one's
        # login call. Same fix as accounts/tests.py, inventory/tests.py, and
        # inventory/tests_movements.py.
        cache.clear()
        self.branch = Branch.objects.create(name="Kimironko")
        self.cashier = User.objects.create_user(
            username="cashier1", password="pw", role=Role.CASHIER, branch=self.branch
        )
        category = Category.objects.create(name="Beverages")
        self.coke = Product.objects.create(
            name="Coca-Cola 500ml", sku="COKE500", category=category, unit_price="1.50", cost_price="0.90"
        )
        self.fanta = Product.objects.create(
            name="Fanta 500ml", sku="FANTA500", category=category, unit_price="1.40", cost_price="0.85"
        )
        services.receive_stock(product=self.coke, branch=self.branch, quantity=100, performed_by=self.cashier)
        services.receive_stock(product=self.fanta, branch=self.branch, quantity=2, performed_by=self.cashier)

        resp = self.client.post(reverse("token_obtain_pair"), {"username": "cashier1", "password": "pw"})
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def _checkout(self, items, payment_method="CASH", idempotency_key=None):
        return self.client.post(
            reverse("checkout"),
            {
                "idempotency_key": str(idempotency_key or uuid.uuid4()),
                "payment_method": payment_method,
                "items": items,
            },
            format="json",
        )

    def test_total_is_computed_server_side_ignoring_client_price(self):
        """The request has no price field at all in the real serializer —
        this test proves that even if a client tries to smuggle one in via
        extra payload fields, it's silently ignored, not honored."""
        resp = self._checkout([
            {"product_id": self.coke.id, "quantity": 2, "unit_price": "0.01"},  # tampered field, should be ignored
        ])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(resp.data["total_amount"]), Decimal("3.00"))  # 2 x real price 1.50, not 0.01

    def test_out_of_stock_line_rolls_back_the_whole_cart(self):
        """Fanta only has 2 in stock; asking for 2 Coke + 5 Fanta must fail
        entirely — including undoing the Coke deduction that already
        happened earlier in the same request."""
        resp = self._checkout([
            {"product_id": self.coke.id, "quantity": 2},
            {"product_id": self.fanta.id, "quantity": 5},
        ])
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Sale.objects.count(), 0)

        # Coke stock must be UNCHANGED — proves the rollback covers the
        # whole transaction, not just the item that actually failed.
        from inventory.models import Stock
        coke_stock = Stock.objects.get(product=self.coke, branch=self.branch)
        self.assertEqual(coke_stock.quantity, 100)

    def test_idempotent_replay_does_not_double_sell(self):
        key = uuid.uuid4()
        first = self._checkout([{"product_id": self.coke.id, "quantity": 3}], idempotency_key=key)
        second = self._checkout([{"product_id": self.coke.id, "quantity": 3}], idempotency_key=key)

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)  # returns existing sale, not a new one
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(Sale.objects.count(), 1)

        from inventory.models import Stock
        coke_stock = Stock.objects.get(product=self.coke, branch=self.branch)
        self.assertEqual(coke_stock.quantity, 97)  # deducted ONCE, not twice

    def test_successful_sale_creates_a_traceable_stock_movement(self):
        resp = self._checkout([{"product_id": self.coke.id, "quantity": 4}])
        sale_id = resp.data["id"]
        movement = StockMovement.objects.filter(
            product=self.coke, reference_object_id=sale_id
        ).first()
        self.assertIsNotNone(movement)
        self.assertEqual(movement.quantity_delta, -4)

    def test_cashier_sells_against_their_own_branch_only(self):
        resp = self._checkout([{"product_id": self.coke.id, "quantity": 1}])
        self.assertEqual(resp.data["branch"], self.branch.id)

    def test_empty_cart_rejected(self):
        resp = self._checkout([])
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_owner_cannot_checkout_without_a_branch(self):
        owner = User.objects.create_user(username="owner", password="pw", role=Role.OWNER)
        resp = self.client.post(reverse("token_obtain_pair"), {"username": "owner", "password": "pw"})
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")
        result = self._checkout([{"product_id": self.coke.id, "quantity": 1}])
        self.assertEqual(result.status_code, status.HTTP_400_BAD_REQUEST)


class CheckoutThrottleTests(APITestCase):
    """A04 - proves the 30/min checkout throttle actually triggers, and
    that it's scoped per-user rather than globally (one busy cashier can't
    lock another one out of their own till)."""

    def setUp(self):
        cache.clear()
        self.branch = Branch.objects.create(name="Kimironko")
        self.cashier = User.objects.create_user(
            username="cashier1", password="pw", role=Role.CASHIER, branch=self.branch
        )
        self.other_cashier = User.objects.create_user(
            username="cashier2", password="pw", role=Role.CASHIER, branch=self.branch
        )
        category = Category.objects.create(name="Beverages")
        self.coke = Product.objects.create(
            name="Coca-Cola 500ml", sku="COKE500", category=category, unit_price="1.50", cost_price="0.90"
        )
        services.receive_stock(product=self.coke, branch=self.branch, quantity=1000, performed_by=self.cashier)

    def _login_as(self, username):
        resp = self.client.post(reverse("token_obtain_pair"), {"username": username, "password": "pw"})
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def _checkout(self):
        return self.client.post(
            reverse("checkout"),
            {
                "idempotency_key": str(uuid.uuid4()),
                "payment_method": "CASH",
                "items": [{"product_id": self.coke.id, "quantity": 1}],
            },
            format="json",
        )

    def test_31st_checkout_in_a_minute_is_throttled(self):
        self._login_as("cashier1")
        statuses = [self._checkout().status_code for _ in range(30)]
        self.assertTrue(all(code == status.HTTP_201_CREATED for code in statuses))

        blocked = self._checkout()
        self.assertEqual(blocked.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_throttle_is_scoped_per_user_not_global(self):
        """cashier1 maxing out their allowance must not affect cashier2 —
        each till gets its own 30/min budget."""
        self._login_as("cashier1")
        for _ in range(30):
            self._checkout()
        self.assertEqual(self._checkout().status_code, status.HTTP_429_TOO_MANY_REQUESTS)

        self._login_as("cashier2")
        self.assertEqual(self._checkout().status_code, status.HTTP_201_CREATED)
