"""
inventory/tests.py

Same pattern as accounts/tests.py: try to break the access control from the
perspective of an authenticated-but-lower-privileged user, and assert it
fails. This is the file to point to when someone asks "how do you know your
multi-branch isolation actually works?"
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role
from branches.models import Branch

from .models import Category, Product, Stock

User = get_user_model()


class InventoryAccessControlTests(APITestCase):
    def setUp(self):
        # ScopedRateThrottle's counters live in the default cache, which
        # persists for the whole test run (not per-test) — clear it so the
        # 5/min login throttle from an earlier test doesn't 429 this one's
        # login call. Same fix as accounts/tests.py.
        cache.clear()
        self.branch_a = Branch.objects.create(name="Kimironko")
        self.branch_b = Branch.objects.create(name="Remera")

        self.owner = User.objects.create_user(username="owner", password="pw", role=Role.OWNER)
        self.manager_a = User.objects.create_user(
            username="manager_a", password="pw", role=Role.MANAGER, branch=self.branch_a
        )
        self.cashier_a = User.objects.create_user(
            username="cashier_a", password="pw", role=Role.CASHIER, branch=self.branch_a
        )
        self.manager_b = User.objects.create_user(
            username="manager_b", password="pw", role=Role.MANAGER, branch=self.branch_b
        )

        category = Category.objects.create(name="Beverages")
        self.product = Product.objects.create(
            name="Coca-Cola 500ml", sku="COKE500", category=category,
            unit_price="1.50", cost_price="0.90", reorder_threshold=20,
        )
        self.stock_a = Stock.objects.create(product=self.product, branch=self.branch_a, quantity=100)
        self.stock_b = Stock.objects.create(product=self.product, branch=self.branch_b, quantity=5)

    def _login(self, username, password="pw"):
        resp = self.client.post(reverse("token_obtain_pair"), {"username": username, "password": password})
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_manager_list_only_shows_own_branch_stock(self):
        self._login("manager_a")
        resp = self.client.get(reverse("stock-list"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        branch_ids = {row["branch"] for row in resp.data}
        self.assertEqual(branch_ids, {self.branch_a.id})

    def test_manager_cannot_fetch_other_branch_stock_by_id(self):
        """The direct-object-access test — this is the actual IDOR check."""
        self._login("manager_a")
        resp = self.client.get(reverse("stock-detail", args=[self.stock_b.id]))
        self.assertIn(resp.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

    def test_owner_sees_all_branches(self):
        self._login("owner")
        resp = self.client.get(reverse("stock-list"))
        branch_ids = {row["branch"] for row in resp.data}
        self.assertEqual(branch_ids, {self.branch_a.id, self.branch_b.id})

    def test_cashier_cannot_edit_product(self):
        self._login("cashier_a")
        resp = self.client.patch(
            reverse("product-detail", args=[self.product.id]), {"unit_price": "99.00"}
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_cashier_response_never_includes_cost_price(self):
        self._login("cashier_a")
        resp = self.client.get(reverse("product-detail", args=[self.product.id]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn("cost_price", resp.data)

    def test_manager_response_does_include_cost_price(self):
        self._login("manager_a")
        resp = self.client.get(reverse("product-detail", args=[self.product.id]))
        self.assertIn("cost_price", resp.data)

    def test_manager_cannot_create_stock_row_in_other_branch(self):
        """
        Even if a manager crafts a request trying to set branch explicitly,
        perform_create() ignores the client-supplied branch and uses the
        authenticated user's own branch instead.
        """
        self._login("manager_a")
        category = Category.objects.get(name="Beverages")
        other_product = Product.objects.create(
            name="Fanta 500ml", sku="FANTA500", category=category, unit_price="1.50", cost_price="0.80"
        )
        resp = self.client.post(
            reverse("stock-list"),
            {"product_id": other_product.id, "branch": self.branch_b.id, "quantity": 999},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        created = Stock.objects.get(product=other_product)
        self.assertEqual(created.branch_id, self.branch_a.id)  # NOT branch_b, despite the payload
