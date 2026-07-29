"""
sales/refund_services.py

Encodes the standard supermarket refund policy as actual enforced rules,
not just UI suggestions:

  1. A return window - most retailers cap returns at 30 days; sales older
     than this are rejected outright, not silently allowed.
  2. Refunds are tied to specific line items from the ORIGINAL sale, never
     a free-floating amount - you can't refund $50 in the abstract, only
     "3 units of this specific SaleItem."
  3. Cumulative validation - you cannot refund more of a line than was
     actually sold, even across multiple partial refund transactions
     (mirrors PurchaseOrderItem.quantity_remaining's exact logic).
  4. Restock is an explicit per-line decision, never inferred.
  5. A reason is mandatory on every refund, same as wastage.
  6. This is the only code path allowed to create a Refund or change
     Sale.status - same "one door in" pattern as every ledger-adjacent
     service in this project.
"""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from inventory.services import record_return

from .models import Refund, RefundItem, Sale, SaleItem, SaleStatus

REFUND_WINDOW_DAYS = 30  # standard retail return window; adjust per business policy


class RefundWindowExpiredError(Exception):
    """Raised when a refund is attempted on a sale older than the return window."""


@transaction.atomic
def process_refund(*, sale: Sale, lines: list, reason: str, performed_by) -> Refund:
    """
    `lines` is a list of {"sale_item_id": int, "quantity": int, "restock": bool}.

    Validates every line BEFORE writing anything - a bad line anywhere in
    the request rejects the whole refund, same atomicity guarantee as
    checkout's multi-item cart rollback.
    """
    if not reason:
        raise ValidationError("A refund must always have a reason.")
    if not lines:
        raise ValidationError("A refund must include at least one item.")

    age = timezone.now() - sale.created_at
    if age > timedelta(days=REFUND_WINDOW_DAYS):
        raise RefundWindowExpiredError(
            f"This sale is {age.days} days old - refunds are only allowed within "
            f"{REFUND_WINDOW_DAYS} days of purchase."
        )
    if sale.status == SaleStatus.REFUNDED:
        raise ValidationError("This sale has already been fully refunded.")

    sale_items = {item.id: item for item in SaleItem.objects.select_for_update().filter(sale=sale)}

    total_refund_amount = 0
    validated_lines = []
    for line in lines:
        sale_item = sale_items.get(line["sale_item_id"])
        if sale_item is None:
            raise ValidationError(f"Sale item {line['sale_item_id']} does not belong to this sale.")
        quantity = line["quantity"]
        if quantity <= 0:
            raise ValidationError("Refund quantity must be positive.")
        remaining = sale_item.quantity - sale_item.quantity_refunded
        if quantity > remaining:
            raise ValidationError(
                f"Cannot refund {quantity} of {sale_item.product.sku} - only "
                f"{remaining} of the original {sale_item.quantity} remain un-refunded."
            )
        total_refund_amount += sale_item.unit_price_at_sale * quantity
        validated_lines.append((sale_item, quantity, line["restock"]))

    refund = Refund.objects.create(
        sale=sale, processed_by=performed_by, reason=reason, total_refunded_amount=total_refund_amount,
    )

    for sale_item, quantity, restock in validated_lines:
        RefundItem.objects.create(refund=refund, sale_item=sale_item, quantity=quantity, restocked=restock)
        sale_item.quantity_refunded += quantity
        sale_item.save(update_fields=["quantity_refunded"])

        if restock:
            # Only restocked items touch the stock ledger - an unsellable
            # (damaged/expired) return was already deducted at sale time
            # and simply doesn't come back; there's no inventory event to
            # record for it beyond the RefundItem row itself, which is
            # already the audit trail for that decision.
            record_return(
                product=sale_item.product, branch=sale.branch, quantity=quantity,
                performed_by=performed_by, reference=refund, reason=reason,
            )

    # Recompute overall sale status from the true cumulative state.
    sale.refresh_from_db()
    all_items = list(sale.items.all())
    if all(i.quantity_refunded >= i.quantity for i in all_items):
        sale.status = SaleStatus.REFUNDED
    elif any(i.quantity_refunded > 0 for i in all_items):
        sale.status = SaleStatus.PARTIALLY_REFUNDED
    sale.save(update_fields=["status"])

    return refund
