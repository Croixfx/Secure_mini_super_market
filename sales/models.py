"""
sales/models.py

A Sale is the business event; a StockMovement (in inventory/) is the
inventory-side consequence of that event. Keeping them as two separate
records — rather than treating "decrement stock" as the whole meaning of a
sale — is what lets a Sale carry receipt/payment concerns (payment method,
receipt number, cashier, idempotency) without polluting the stock ledger,
and lets the stock ledger stay a pure, generic "quantity changed, here's
why" record usable by sales, transfers, and procurement alike.
"""
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class PaymentMethod(models.TextChoices):
    CASH = "CASH", "Cash"
    MOMO = "MOMO", "Mobile Money"


class SaleStatus(models.TextChoices):
    COMPLETED = "COMPLETED", "Completed"
    REFUNDED = "REFUNDED", "Refunded"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED", "Partially refunded"


class Sale(models.Model):
    """
    One row per completed transaction. `idempotency_key` is what makes
    checkout safe to retry — if a POS resubmits after a network blip (or an
    offline-queued sale finally syncs), the same key returns the same Sale
    rather than creating a duplicate and double-deducting stock.
    """

    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="sales")
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sales")

    idempotency_key = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)

    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    status = models.CharField(max_length=20, choices=SaleStatus.choices, default=SaleStatus.COMPLETED)

    # Computed and stored SERVER-SIDE at checkout time, from Product.unit_price
    # at that moment — never trusted from the client, and never recomputed
    # later from current prices (a price change next week must not silently
    # rewrite last week's receipt total).
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["branch", "created_at"]),
            models.Index(fields=["cashier", "created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Sale #{self.id} @ {self.branch} — {self.total_amount}"


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT, related_name="sale_items")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    # Price AT THE TIME of sale — same reasoning as Sale.total_amount.
    unit_price_at_sale = models.DecimalField(max_digits=10, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.quantity}x {self.product.sku} @ {self.unit_price_at_sale}"
