"""
sales/tests_refunds.py

Each test proves one policy rule from process_refund(), not just that the
endpoint returns a status code:
- restocked items actually go back through the ledger, non-restocked don't
- you cannot refund more than was originally sold, even across two
  separate partial refunds
- an expired return window is enforced, not just documented
- a cashier cannot process a refund, even for their own sale
"""
import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role
from branches.models import Branch
from django.core.cache import cache
from inventory import services as inventory_services
from inventory.models import Category, Product, Stock

from .models import Sale, SaleItem, SaleStatus
from .refund_services import REFUND_WINDOW_DAYS

User = get_user_model()


class RefundTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.branch = Branch.objects.create(name="Kimironko")
        self.manager = User.objects.create_user(
            username="manager1", password="pw", role=Role.MANAGER, branch=self.branch
        )
        self.cashier = User.objects.create_user(
            username="cashier1", password="pw", role=Role.CASHIER, branch=self.branch
        )
        category = Category.objects.create(name="Beverages")
        self.coke = Product.objects.create(
            name="Coca-Cola 500ml", sku="COKE500", category=category, unit_price="1.50", cost_price="0.90"
        )
        inventory_services.receive_stock(product=self.coke, branch=self.branch, quantity=100, performed_by=self.manager)

        self.sale = Sale.objects.create(
            branch=self.branch, cashier=self.cashier, idempotency_key=uuid.uuid4(),
            payment_method="CASH", total_amount=Decimal("15.00"),
        )
        self.sale_item = SaleItem.objects.create(
            sale=self.sale, product=self.coke, quantity=10,
            unit_price_at_sale=Decimal("1.50"), line_total=Decimal("15.00"),
        )
        # Sale already deducted stock in the real checkout flow - mirror
        # that here so the "restock brings it back" assertion is meaningful.
        inventory_services.record_sale(product=self.coke, branch=self.branch, quantity=10, performed_by=self.cashier, reference=self.sale)

        self._login("manager1")

    def _login(self, username, password="pw"):
        resp = self.client.post(reverse("token_obtain_pair"), {"username": username, "password": password})
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def _refund(self, lines, reason="customer return"):
        return self.client.post(
            reverse("sale-refund", args=[self.sale.id]),
            {"reason": reason, "lines": lines}, format="json",
        )

    def test_restocked_refund_increases_stock(self):
        stock_before = Stock.objects.get(product=self.coke, branch=self.branch).quantity
        resp = self._refund([{"sale_item_id": self.sale_item.id, "quantity": 3, "restock": True}])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        stock_after = Stock.objects.get(product=self.coke, branch=self.branch).quantity
        self.assertEqual(stock_after, stock_before + 3)

    def test_non_restocked_refund_does_not_touch_stock(self):
        stock_before = Stock.objects.get(product=self.coke, branch=self.branch).quantity
        resp = self._refund([{"sale_item_id": self.sale_item.id, "quantity": 2, "restock": False}], reason="expired on return")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        stock_after = Stock.objects.get(product=self.coke, branch=self.branch).quantity
        self.assertEqual(stock_after, stock_before)  # unchanged - item was unsellable

    def test_partial_refund_marks_sale_partially_refunded(self):
        resp = self._refund([{"sale_item_id": self.sale_item.id, "quantity": 4, "restock": True}])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, SaleStatus.PARTIALLY_REFUNDED)

    def test_full_refund_marks_sale_refunded(self):
        self._refund([{"sale_item_id": self.sale_item.id, "quantity": 10, "restock": True}])
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, SaleStatus.REFUNDED)

    def test_cannot_refund_more_than_originally_sold_across_two_calls(self):
        first = self._refund([{"sale_item_id": self.sale_item.id, "quantity": 7, "restock": True}])
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        second = self._refund([{"sale_item_id": self.sale_item.id, "quantity": 5, "restock": True}])  # 7+5=12 > 10 sold
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.sale_item.refresh_from_db()
        self.assertEqual(self.sale_item.quantity_refunded, 7)  # second call must not have applied partially

    def test_refund_amount_computed_from_original_sale_price_not_client(self):
        resp = self._refund([{"sale_item_id": self.sale_item.id, "quantity": 2, "restock": True}])
        self.assertEqual(Decimal(resp.data["total_refunded_amount"]), Decimal("3.00"))  # 2 x 1.50

    def test_reason_is_required(self):
        resp = self._refund([{"sale_item_id": self.sale_item.id, "quantity": 1, "restock": True}], reason="")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_refund_rejected_outside_the_return_window(self):
        self.sale.created_at = timezone.now() - timedelta(days=REFUND_WINDOW_DAYS + 5)
        self.sale.save(update_fields=["created_at"])
        resp = self._refund([{"sale_item_id": self.sale_item.id, "quantity": 1, "restock": True}])
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cashier_cannot_process_a_refund_even_for_their_own_sale(self):
        self._login("cashier1")
        resp = self._refund([{"sale_item_id": self.sale_item.id, "quantity": 1, "restock": True}])
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_cannot_refund_another_branchs_sale(self):
        other_branch = Branch.objects.create(name="Remera")
        other_manager = User.objects.create_user(
            username="manager2", password="pw", role=Role.MANAGER, branch=other_branch
        )
        self._login("manager2")
        resp = self._refund([{"sale_item_id": self.sale_item.id, "quantity": 1, "restock": True}])
        self.assertIn(resp.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))
