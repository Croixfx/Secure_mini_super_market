"""
inventory/tests_transfers.py

New file, drops into inventory/ as-is.

Each test proves a property of the design, not just a status code:
- stock does NOT move at REQUESTED, only at IN_TRANSIT (dispatch)
- only the source branch can dispatch; only the destination can receive
- receiving fewer units than dispatched is tracked as a real discrepancy,
  not silently absorbed
- cancellation is blocked once dispatched
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role
from branches.models import Branch

from . import services as inventory_services
from .models import Category, Product, Stock

User = get_user_model()


class StockTransferTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.branch_a = Branch.objects.create(name="Kimironko")
        self.branch_b = Branch.objects.create(name="Remera")
        self.manager_a = User.objects.create_user(
            username="manager_a", password="pw", role=Role.MANAGER, branch=self.branch_a
        )
        self.manager_b = User.objects.create_user(
            username="manager_b", password="pw", role=Role.MANAGER, branch=self.branch_b
        )
        category = Category.objects.create(name="Beverages")
        self.coke = Product.objects.create(
            name="Coca-Cola 500ml", sku="COKE500", category=category, unit_price="1.50", cost_price="0.90"
        )
        inventory_services.receive_stock(product=self.coke, branch=self.branch_a, quantity=100, performed_by=self.manager_a)
        self._login("manager_a")

    def _login(self, username, password="pw"):
        resp = self.client.post(reverse("token_obtain_pair"), {"username": username, "password": password})
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def _request(self, quantity=20):
        return self.client.post(reverse("stocktransfer-list"), {
            "product": self.coke.id, "from_branch": self.branch_a.id,
            "to_branch": self.branch_b.id, "quantity": quantity,
        }, format="json")

    def test_stock_unchanged_at_request_stage(self):
        stock_before = Stock.objects.get(product=self.coke, branch=self.branch_a).quantity
        resp = self._request(30)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["status"], "REQUESTED")
        stock_after = Stock.objects.get(product=self.coke, branch=self.branch_a).quantity
        self.assertEqual(stock_before, stock_after)  # nothing moved yet

    def test_dispatch_removes_stock_from_source(self):
        transfer_id = self._request(30).data["id"]
        resp = self.client.post(reverse("stocktransfer-dispatch", args=[transfer_id]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], "IN_TRANSIT")
        stock = Stock.objects.get(product=self.coke, branch=self.branch_a).quantity
        self.assertEqual(stock, 70)  # 100 - 30

    def test_only_source_branch_can_dispatch(self):
        transfer_id = self._request(30).data["id"]
        self._login("manager_b")  # destination branch, not source
        resp = self.client.post(reverse("stocktransfer-dispatch", args=[transfer_id]))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_only_destination_branch_can_receive(self):
        transfer_id = self._request(30).data["id"]
        self.client.post(reverse("stocktransfer-dispatch", args=[transfer_id]))
        # still logged in as manager_a (source) - should NOT be able to receive
        resp = self.client.post(reverse("stocktransfer-receive", args=[transfer_id]), {"quantity_received": 30}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_full_receive_adds_stock_to_destination_with_no_discrepancy(self):
        transfer_id = self._request(30).data["id"]
        self.client.post(reverse("stocktransfer-dispatch", args=[transfer_id]))
        self._login("manager_b")
        resp = self.client.post(reverse("stocktransfer-receive", args=[transfer_id]), {"quantity_received": 30}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], "RECEIVED")
        self.assertEqual(resp.data["discrepancy"], 0)
        dest_stock = Stock.objects.get(product=self.coke, branch=self.branch_b).quantity
        self.assertEqual(dest_stock, 30)

    def test_partial_receive_tracks_discrepancy(self):
        """Simulates breakage in transit - 30 dispatched, only 27 arrive intact."""
        transfer_id = self._request(30).data["id"]
        self.client.post(reverse("stocktransfer-dispatch", args=[transfer_id]))
        self._login("manager_b")
        resp = self.client.post(reverse("stocktransfer-receive", args=[transfer_id]), {"quantity_received": 27}, format="json")
        self.assertEqual(resp.data["discrepancy"], 3)
        dest_stock = Stock.objects.get(product=self.coke, branch=self.branch_b).quantity
        self.assertEqual(dest_stock, 27)  # only what actually arrived, not what was dispatched

    def test_cannot_receive_before_dispatch(self):
        transfer_id = self._request(30).data["id"]
        self._login("manager_b")
        resp = self.client.post(reverse("stocktransfer-receive", args=[transfer_id]), {"quantity_received": 30}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_dispatch_fails_cleanly_if_source_lacks_stock(self):
        transfer_id = self._request(500).data["id"]  # more than the 100 in stock
        resp = self.client.post(reverse("stocktransfer-dispatch", args=[transfer_id]))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        stock = Stock.objects.get(product=self.coke, branch=self.branch_a).quantity
        self.assertEqual(stock, 100)  # unchanged - failed dispatch shouldn't partially deduct

    def test_can_cancel_before_dispatch(self):
        transfer_id = self._request(30).data["id"]
        resp = self.client.post(reverse("stocktransfer-cancel", args=[transfer_id]))
        self.assertEqual(resp.data["status"], "CANCELLED")

    def test_cannot_cancel_after_dispatch(self):
        transfer_id = self._request(30).data["id"]
        self.client.post(reverse("stocktransfer-dispatch", args=[transfer_id]))
        resp = self.client.post(reverse("stocktransfer-cancel", args=[transfer_id]))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cashier_cannot_access_transfers(self):
        User.objects.create_user(username="cashier_a", password="pw", role=Role.CASHIER, branch=self.branch_a)
        self._login("cashier_a")
        resp = self.client.get(reverse("stocktransfer-list"))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_cannot_request_transfer_between_two_unrelated_branches(self):
        branch_c = Branch.objects.create(name="Nyamirambo")
        resp = self.client.post(reverse("stocktransfer-list"), {
            "product": self.coke.id, "from_branch": self.branch_b.id,  # manager_a is at branch_a, neither side here
            "to_branch": branch_c.id, "quantity": 10,
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
