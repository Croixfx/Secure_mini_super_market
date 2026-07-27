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

    This is the table every branch-scoping bug would surface in first —
    if a queryset here isn't filtered by request.user.branch, a cashier at
    branch B can see (or worse, decrement) branch A's stock.
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
