"""
procurement/models.py

This is the piece that completes the chain: Supplier -> PurchaseOrder ->
(receiving) -> inventory.services.receive_stock() -> StockMovement ->
Stock.quantity. Before this app existed, stock only ever entered the
system through a seed script or a Django shell — this is the first real,
user-facing path for "restock the shelf."

Suppliers are NOT branch-scoped (a supplier typically serves every
branch); PurchaseOrders ARE branch-scoped (each branch orders for itself).
"""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Supplier(models.Model):
    name = models.CharField(max_length=200, unique=True)
    contact_name = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class PurchaseOrderStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SENT = "SENT", "Sent"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED", "Partially received"
    RECEIVED = "RECEIVED", "Received"
    CANCELLED = "CANCELLED", "Cancelled"


class PurchaseOrder(models.Model):
    """
    One order to one supplier, for one branch. Status moves forward through
    DRAFT -> SENT -> (PARTIALLY_RECEIVED ->) RECEIVED, or DRAFT/SENT ->
    CANCELLED. Status transitions are enforced in services.py, not left to
    the client to set directly — see the same reasoning as the
    StockTransfer state-machine discussion earlier in this project.
    """

    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_orders")
    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="purchase_orders")
    status = models.CharField(max_length=20, choices=PurchaseOrderStatus.choices, default=PurchaseOrderStatus.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="purchase_orders")
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["branch", "status"])]

    def __str__(self):
        return f"PO #{self.id} — {self.supplier.name} ({self.status})"


class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT, related_name="purchase_order_items")
    quantity_ordered = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    quantity_received = models.PositiveIntegerField(default=0)

    # Cost negotiated for THIS order — never read from Product.cost_price,
    # since that can drift over time and this is what actually gets paid.
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])

    # Captured at order time where known; used when receiving so batch/expiry
    # travel into the resulting StockMovement automatically.
    batch_number = models.CharField(max_length=100, blank=True)
    expiry_date = models.DateField(null=True, blank=True)

    @property
    def quantity_remaining(self):
        return self.quantity_ordered - self.quantity_received

    def __str__(self):
        return f"{self.quantity_ordered}x {self.product.sku} ({self.quantity_received} received)"
