"""
procurement/tests.py

Each test proves a property, not just that an endpoint returns 200:
- receiving a PO actually writes a traceable StockMovement via the ledger
- partial receiving is genuinely partial (can't over-receive, status
  reflects reality)
- illegal status transitions are rejected (can't receive a draft order,
  can't send an already-sent order)
- branch scoping matches every other feature in this project
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role
from branches.models import Branch
from inventory.models import Category, Product, Stock, StockMovement

from . import services
from .models import PurchaseOrder, PurchaseOrderStatus, Supplier

User = get_user_model()


class PurchaseOrderLifecycleTests(APITestCase):
    def setUp(self):
        # ScopedRateThrottle's counters live in the default cache, which
        # persists for the whole test run (not per-test) — clear it so the
        # 5/min login throttle from an earlier test doesn't 429 this one's
        # login call. Same fix as accounts/tests.py, sales/tests.py, and
        # inventory/tests.py.
        cache.clear()
        self.branch = Branch.objects.create(name="Kimironko")
        self.manager = User.objects.create_user(
            username="manager1", password="pw", role=Role.MANAGER, branch=self.branch
        )
        self.cashier = User.objects.create_user(
            username="cashier1", password="pw", role=Role.CASHIER, branch=self.branch
        )
        self.supplier = Supplier.objects.create(name="BrightSky Electronics", email="hi@brightsky.test")
        category = Category.objects.create(name="Beverages")
        self.coke = Product.objects.create(
            name="Coca-Cola 500ml", sku="COKE500", category=category, unit_price="1.50", cost_price="0.90"
        )
        self._login("manager1")

    def _login(self, username, password="pw"):
        resp = self.client.post(reverse("token_obtain_pair"), {"username": username, "password": password})
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def _create_order(self, quantity=100, unit_cost="0.85"):
        resp = self.client.post(reverse("purchaseorder-list"), {
            "supplier": self.supplier.id,
            "items": [{"product": self.coke.id, "quantity_ordered": quantity, "unit_cost": unit_cost}],
        }, format="json")
        return resp

    def test_create_order_defaults_to_draft_and_assigns_branch_server_side(self):
        resp = self._create_order()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["status"], "DRAFT")
        self.assertEqual(resp.data["branch"], self.branch.id)

    def test_cannot_receive_a_draft_order(self):
        po = PurchaseOrder.objects.get(id=self._create_order().data["id"])
        item_id = po.items.first().id
        resp = self.client.post(
            reverse("purchaseorder-receive", args=[po.id]), {"receipts": [{"item_id": item_id, "quantity": 10}]}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_send_then_receive_full_quantity_updates_ledger_and_stock(self):
        po_id = self._create_order(quantity=100, unit_cost="0.85").data["id"]
        self.client.post(reverse("purchaseorder-send", args=[po_id]))
        po = PurchaseOrder.objects.get(id=po_id)
        item = po.items.first()

        resp = self.client.post(
            reverse("purchaseorder-receive", args=[po_id]),
            {"receipts": [{"item_id": item.id, "quantity": 100}]}, format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], "RECEIVED")

        stock = Stock.objects.get(product=self.coke, branch=self.branch)
        self.assertEqual(stock.quantity, 100)

        movement = StockMovement.objects.filter(product=self.coke, movement_type="RECEIPT").first()
        self.assertIsNotNone(movement)
        self.assertEqual(movement.reference_object_id, po_id)
        self.assertEqual(movement.unit_cost, item.unit_cost)

    def test_partial_receive_keeps_order_open_and_tracks_remaining(self):
        po_id = self._create_order(quantity=100).data["id"]
        self.client.post(reverse("purchaseorder-send", args=[po_id]))
        po = PurchaseOrder.objects.get(id=po_id)
        item = po.items.first()

        resp = self.client.post(
            reverse("purchaseorder-receive", args=[po_id]),
            {"receipts": [{"item_id": item.id, "quantity": 40}]}, format="json",
        )
        self.assertEqual(resp.data["status"], "PARTIALLY_RECEIVED")
        item.refresh_from_db()
        self.assertEqual(item.quantity_received, 40)
        self.assertEqual(item.quantity_remaining, 60)

        # Second delivery completes it.
        resp2 = self.client.post(
            reverse("purchaseorder-receive", args=[po_id]),
            {"receipts": [{"item_id": item.id, "quantity": 60}]}, format="json",
        )
        self.assertEqual(resp2.data["status"], "RECEIVED")

        stock = Stock.objects.get(product=self.coke, branch=self.branch)
        self.assertEqual(stock.quantity, 100)  # 40 + 60, not double-counted

    def test_cannot_over_receive_beyond_ordered_quantity(self):
        po_id = self._create_order(quantity=50).data["id"]
        self.client.post(reverse("purchaseorder-send", args=[po_id]))
        po = PurchaseOrder.objects.get(id=po_id)
        item = po.items.first()

        resp = self.client.post(
            reverse("purchaseorder-receive", args=[po_id]),
            {"receipts": [{"item_id": item.id, "quantity": 999}]}, format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        stock_exists = Stock.objects.filter(product=self.coke, branch=self.branch).exists()
        self.assertFalse(stock_exists)  # nothing should have been received

    def test_cannot_send_an_already_sent_order(self):
        po_id = self._create_order().data["id"]
        self.client.post(reverse("purchaseorder-send", args=[po_id]))
        resp = self.client.post(reverse("purchaseorder-send", args=[po_id]))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cashier_cannot_create_or_view_purchase_orders(self):
        self._login("cashier1")
        resp = self._create_order()
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        list_resp = self.client.get(reverse("purchaseorder-list"))
        self.assertEqual(list_resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_cannot_see_other_branch_orders(self):
        other_branch = Branch.objects.create(name="Remera")
        other_manager = User.objects.create_user(
            username="manager2", password="pw", role=Role.MANAGER, branch=other_branch
        )
        self._create_order()  # created by manager1 @ Kimironko

        self._login("manager2")
        resp = self.client.get(reverse("purchaseorder-list"))
        self.assertEqual(len(resp.data), 0)

    def test_cancel_order_before_receiving(self):
        po_id = self._create_order().data["id"]
        resp = self.client.post(reverse("purchaseorder-cancel", args=[po_id]))
        self.assertEqual(resp.data["status"], "CANCELLED")

    def test_cannot_cancel_a_received_order(self):
        po_id = self._create_order(quantity=10).data["id"]
        self.client.post(reverse("purchaseorder-send", args=[po_id]))
        po = PurchaseOrder.objects.get(id=po_id)
        item = po.items.first()
        self.client.post(
            reverse("purchaseorder-receive", args=[po_id]),
            {"receipts": [{"item_id": item.id, "quantity": 10}]}, format="json",
        )
        resp = self.client.post(reverse("purchaseorder-cancel", args=[po_id]))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
