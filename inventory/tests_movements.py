"""
inventory/tests_movements.py

These tests exist to prove the properties that actually matter for
"traceable stock," not just that the models can be created:

1. Stock.quantity always equals the sum of every StockMovement for that
   (product, branch) — the cache never drifts from the ledger.
2. A movement that would take stock negative is rejected, UNLESS it's a
   stocktake correction.
3. Every movement carries who did it and (when relevant) why.
4. Branch scoping applies to the movement ledger exactly like it does to
   Stock itself.
"""
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role
from branches.models import Branch

from . import services
from .models import Category, MovementType, Product, Stock, StockMovement

User = get_user_model()


class LedgerIntegrityTests(TestCase):
    """Plain Django TestCase — these are about data integrity, not API access."""

    def setUp(self):
        self.branch = Branch.objects.create(name="Kimironko")
        self.user = User.objects.create_user(username="manager", password="pw", role=Role.MANAGER, branch=self.branch)
        category = Category.objects.create(name="Beverages")
        self.product = Product.objects.create(
            name="Coca-Cola 500ml", sku="COKE500", category=category,
            unit_price="1.50", cost_price="0.90", reorder_threshold=20,
        )

    def _ledger_sum(self):
        return StockMovement.objects.filter(product=self.product, branch=self.branch).aggregate(
            total=Sum("quantity_delta")
        )["total"] or 0

    def test_receipt_then_sale_cache_matches_ledger_sum(self):
        services.receive_stock(product=self.product, branch=self.branch, quantity=100, performed_by=self.user)
        services.record_sale(product=self.product, branch=self.branch, quantity=15, performed_by=self.user)
        services.record_sale(product=self.product, branch=self.branch, quantity=3, performed_by=self.user)

        stock = Stock.objects.get(product=self.product, branch=self.branch)
        self.assertEqual(stock.quantity, 82)
        self.assertEqual(stock.quantity, self._ledger_sum())

    def test_sale_exceeding_stock_is_rejected_and_leaves_no_partial_state(self):
        services.receive_stock(product=self.product, branch=self.branch, quantity=5, performed_by=self.user)
        with self.assertRaises(services.InsufficientStockError):
            services.record_sale(product=self.product, branch=self.branch, quantity=10, performed_by=self.user)

        # The rejected attempt must not have written a movement OR changed
        # the cached quantity — the whole operation is atomic.
        stock = Stock.objects.get(product=self.product, branch=self.branch)
        self.assertEqual(stock.quantity, 5)
        self.assertEqual(self._ledger_sum(), 5)
        self.assertEqual(
            StockMovement.objects.filter(product=self.product, movement_type=MovementType.SALE).count(), 0
        )

    def test_stocktake_can_correct_downward_and_is_the_only_negative_capable_path(self):
        services.receive_stock(product=self.product, branch=self.branch, quantity=50, performed_by=self.user)
        # Physical count found only 44 — 6 units unaccounted for (shrinkage).
        movement = services.record_stocktake_adjustment(
            product=self.product, branch=self.branch, counted_quantity=44, performed_by=self.user,
        )
        self.assertEqual(movement.quantity_delta, -6)
        stock = Stock.objects.get(product=self.product, branch=self.branch)
        self.assertEqual(stock.quantity, 44)
        self.assertEqual(stock.quantity, self._ledger_sum())

    def test_stocktake_with_no_discrepancy_writes_nothing(self):
        services.receive_stock(product=self.product, branch=self.branch, quantity=20, performed_by=self.user)
        result = services.record_stocktake_adjustment(
            product=self.product, branch=self.branch, counted_quantity=20, performed_by=self.user,
        )
        self.assertIsNone(result)
        self.assertEqual(
            StockMovement.objects.filter(movement_type=MovementType.STOCKTAKE_ADJUSTMENT).count(), 0
        )

    def test_wastage_requires_a_reason(self):
        services.receive_stock(product=self.product, branch=self.branch, quantity=10, performed_by=self.user)
        with self.assertRaises(Exception):
            services.record_wastage(
                product=self.product, branch=self.branch, quantity=2, performed_by=self.user, reason=""
            )

    def test_every_movement_records_who_performed_it(self):
        movement = services.receive_stock(
            product=self.product, branch=self.branch, quantity=10, performed_by=self.user
        )
        self.assertEqual(movement.performed_by, self.user)

    def test_transfer_out_and_in_are_separate_traceable_events(self):
        branch_b = Branch.objects.create(name="Remera")
        services.receive_stock(product=self.product, branch=self.branch, quantity=50, performed_by=self.user)

        out_movement = services.transfer_out(
            product=self.product, branch=self.branch, quantity=20, performed_by=self.user
        )
        in_movement = services.transfer_in(
            product=self.product, branch=branch_b, quantity=20, performed_by=self.user
        )

        self.assertEqual(Stock.objects.get(product=self.product, branch=self.branch).quantity, 30)
        self.assertEqual(Stock.objects.get(product=self.product, branch=branch_b).quantity, 20)
        # Two distinct ledger rows, not one — each branch's history stays intact.
        self.assertNotEqual(out_movement.id, in_movement.id)
        self.assertEqual(out_movement.movement_type, MovementType.TRANSFER_OUT)
        self.assertEqual(in_movement.movement_type, MovementType.TRANSFER_IN)


class MovementApiAccessControlTests(APITestCase):
    """Branch scoping and role restriction on the movement ledger + action endpoints."""

    def setUp(self):
        self.branch_a = Branch.objects.create(name="Kimironko")
        self.branch_b = Branch.objects.create(name="Remera")
        self.manager_a = User.objects.create_user(
            username="manager_a", password="pw", role=Role.MANAGER, branch=self.branch_a
        )
        self.cashier_a = User.objects.create_user(
            username="cashier_a", password="pw", role=Role.CASHIER, branch=self.branch_a
        )
        category = Category.objects.create(name="Beverages")
        self.product = Product.objects.create(
            name="Coca-Cola 500ml", sku="COKE500", category=category, unit_price="1.50", cost_price="0.90"
        )
        services.receive_stock(product=self.product, branch=self.branch_a, quantity=50, performed_by=self.manager_a)
        services.receive_stock(product=self.product, branch=self.branch_b, quantity=30, performed_by=self.manager_a)

    def _login(self, username, password="pw"):
        resp = self.client.post(reverse("token_obtain_pair"), {"username": username, "password": password})
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_movement_list_only_shows_own_branch(self):
        self._login("manager_a")
        resp = self.client.get(reverse("movement-list"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        branch_names = {row["branch_name"] for row in resp.data}
        self.assertEqual(branch_names, {"Kimironko"})

    def test_cashier_cannot_record_wastage(self):
        self._login("cashier_a")
        resp = self.client.post(
            reverse("stock-record-wastage"), {"product": self.product.id, "quantity": 2, "reason": "expired"}
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_can_record_wastage_and_it_appears_in_ledger(self):
        self._login("manager_a")
        resp = self.client.post(
            reverse("stock-record-wastage"), {"product": self.product.id, "quantity": 2, "reason": "expired"}
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            StockMovement.objects.filter(movement_type=MovementType.WASTAGE, branch=self.branch_a).count(), 1
        )

    def test_wastage_without_reason_is_rejected_by_serializer(self):
        self._login("manager_a")
        resp = self.client.post(
            reverse("stock-record-wastage"), {"product": self.product.id, "quantity": 2, "reason": ""}
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
