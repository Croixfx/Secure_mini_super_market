"""
inventory/models.py

OWASP mapping carried over from accounts:
- A01: Stock is per-branch by design (FK), not a global quantity — this is
  what makes branch-scoped queryset filtering meaningful. There is no
  "global quantity" field anywhere for a manager/cashier to accidentally
  see or edit across branches.
"""
from decimal import Decimal

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MinValueValidator
from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Product(models.Model):
    """
    Product catalog is global (a can of beans is the same SKU everywhere) —
    only STOCK QUANTITY is per-branch. This split matters: if quantity lived
    on Product directly, you couldn't represent "50 units at branch A, 12 at
    branch B" without either duplicating products per branch (data
    integrity nightmare) or bolting on a branch field that half the app
    forgets to filter by.
    """

    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=64, unique=True)
    barcode = models.CharField(max_length=64, unique=True, null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    reorder_threshold = models.PositiveIntegerField(default=10)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.sku})"


class Stock(models.Model):
    """
    The per-branch quantity record. One row per (product, branch) pair.

    IMPORTANT: `quantity` is a CACHED, DERIVED value — the real source of
    truth is the sum of every StockMovement row for this (product, branch)
    pair. Nothing should ever set `quantity` directly except
    `services.apply_movement()`, which writes the StockMovement first and
    updates this cache in the same atomic transaction.

    Why cache it at all, if StockMovement is the source of truth? Because
    "what's the current stock level" is the single most frequent read in
    the whole system (every POS screen load, every stock list), and summing
    a ledger table on every read doesn't scale. This is the standard
    event-sourcing-with-a-projection pattern: full history in the ledger,
    fast reads from a maintained snapshot.
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="stock_records")
    branch = models.ForeignKey("branches.Branch", on_delete=models.CASCADE, related_name="stock_records")
    quantity = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("product", "branch")
        indexes = [models.Index(fields=["branch", "product"])]

    def is_below_threshold(self) -> bool:
        return self.quantity < self.product.reorder_threshold

    def __str__(self):
        return f"{self.product.sku} @ {self.branch} = {self.quantity}"


class MovementType(models.TextChoices):
    RECEIPT = "RECEIPT", "Goods received"
    SALE = "SALE", "Sale"
    RETURN = "RETURN", "Customer return"
    TRANSFER_OUT = "TRANSFER_OUT", "Transfer out (to another branch)"
    TRANSFER_IN = "TRANSFER_IN", "Transfer in (from another branch)"
    WASTAGE = "WASTAGE", "Wastage / spoilage / damage"
    STOCKTAKE_ADJUSTMENT = "STOCKTAKE_ADJUSTMENT", "Physical count correction"


class StockMovement(models.Model):
    """
    Append-only ledger. One row per event that ever changed a stock level,
    at any branch, ever. This table is never updated or deleted after
    creation — a correction is always a NEW row, never an edit to an old
    one (the same principle as double-entry bookkeeping, and the same
    "accounting" pillar the accounts app applies to logins).

    `quantity_delta` is signed: positive for anything that adds stock
    (RECEIPT, RETURN, TRANSFER_IN), negative for anything that removes it
    (SALE, TRANSFER_OUT, WASTAGE). STOCKTAKE_ADJUSTMENT can be either sign,
    since a physical count can come in higher or lower than the system
    expected.

    `reference_type`/`reference_id`/`reference` (GenericForeignKey) point
    at WHATEVER caused this movement — a Sale, a PurchaseOrder, a
    StockTransfer, or nothing (a manual wastage entry). This is what makes
    a movement traceable: given a StockMovement row, you can always answer
    "what caused this" by following the reference, not by guessing from a
    timestamp and hoping it lines up with something else in the system.
    """

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="movements")
    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="movements")
    movement_type = models.CharField(max_length=30, choices=MovementType.choices)
    quantity_delta = models.IntegerField(help_text="Signed. Positive adds stock, negative removes it.")

    # Batch/expiry — populated for RECEIPT movements (and carried forward on
    # TRANSFER_IN/TRANSFER_OUT so a batch's expiry stays traceable across
    # branches), null for movements where a batch isn't meaningful (a sale
    # doesn't need its own batch number if you're not doing batch-level
    # picking yet — see note in services.py about FEFO as a future step).
    batch_number = models.CharField(max_length=100, null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)

    # Cost captured AT THE TIME of this movement — never look this up from
    # Product.cost_price later, because that field can change. This is what
    # lets margin reports be historically accurate even after prices change.
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    reason = models.CharField(
        max_length=255, blank=True,
        help_text="Free text, mainly for WASTAGE (e.g. 'expired', 'dropped', 'damaged in transit') "
                   "and STOCKTAKE_ADJUSTMENT (e.g. 'annual count, June 2026').",
    )

    # Generic reference to whatever domain object caused this movement.
    reference_content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True
    )
    reference_object_id = models.PositiveIntegerField(null=True, blank=True)
    reference = GenericForeignKey("reference_content_type", "reference_object_id")

    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="stock_movements"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["product", "branch", "created_at"]),
            models.Index(fields=["movement_type", "created_at"]),
            models.Index(fields=["reference_content_type", "reference_object_id"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        sign = "+" if self.quantity_delta >= 0 else ""
        return f"{self.movement_type} {sign}{self.quantity_delta} {self.product.sku} @ {self.branch}"
