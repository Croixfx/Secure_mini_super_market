"""
procurement/services.py

Same pattern as inventory/services.py: this is the only code path allowed
to change a PurchaseOrder's status or record a receipt. Views call these
functions; they never set `status` or `quantity_received` directly.
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from inventory.services import receive_stock

from .models import PurchaseOrder, PurchaseOrderStatus


class InvalidTransitionError(Exception):
    """Raised when a status change doesn't follow the allowed order lifecycle."""


def send_order(*, purchase_order: PurchaseOrder, performed_by):
    if purchase_order.status != PurchaseOrderStatus.DRAFT:
        raise InvalidTransitionError(
            f"Only a draft order can be sent (current status: {purchase_order.status})."
        )
    if not purchase_order.items.exists():
        raise ValidationError("Cannot send an order with no items.")
    purchase_order.status = PurchaseOrderStatus.SENT
    purchase_order.sent_at = timezone.now()
    purchase_order.save(update_fields=["status", "sent_at"])
    return purchase_order


@transaction.atomic
def receive_items(*, purchase_order: PurchaseOrder, receipts: list, performed_by):
    """
    `receipts` is a list of {"item_id": int, "quantity": int} — how much of
    each line is being received in THIS delivery (a supplier may deliver a
    partial shipment, so this can be called more than once per order).

    For each line:
      1. Validate the order is in a receivable state (SENT or already
         PARTIALLY_RECEIVED — not DRAFT, RECEIVED, or CANCELLED).
      2. Validate the quantity doesn't exceed what's still outstanding on
         that line.
      3. Call inventory.services.receive_stock() — this is the ONLY place
         stock actually increases, carrying the item's batch/expiry/cost
         forward and tagging the resulting StockMovement with a reference
         back to this PurchaseOrder.
      4. Update quantity_received on the item.

    After processing every line, recompute the order's overall status:
    RECEIVED if every line is fully received, PARTIALLY_RECEIVED if some
    but not all quantity has arrived, unchanged otherwise.
    """
    if purchase_order.status not in (PurchaseOrderStatus.SENT, PurchaseOrderStatus.PARTIALLY_RECEIVED):
        raise InvalidTransitionError(
            f"Cannot receive against a {purchase_order.status} order — it must be SENT first."
        )

    items_by_id = {item.id: item for item in purchase_order.items.select_for_update()}

    for receipt in receipts:
        item = items_by_id.get(receipt["item_id"])
        if item is None:
            raise ValidationError(f"Item {receipt['item_id']} does not belong to this purchase order.")
        quantity = receipt["quantity"]
        if quantity <= 0:
            raise ValidationError("Received quantity must be positive.")
        if quantity > item.quantity_remaining:
            raise ValidationError(
                f"Cannot receive {quantity} of {item.product.sku} — only "
                f"{item.quantity_remaining} remain outstanding on this order."
            )

        receive_stock(
            product=item.product,
            branch=purchase_order.branch,
            quantity=quantity,
            performed_by=performed_by,
            batch_number=item.batch_number,
            expiry_date=item.expiry_date,
            unit_cost=item.unit_cost,
            reference=purchase_order,
        )
        item.quantity_received += quantity
        item.save(update_fields=["quantity_received"])

    purchase_order.refresh_from_db()
    all_items = list(purchase_order.items.all())
    if all(i.quantity_received >= i.quantity_ordered for i in all_items):
        purchase_order.status = PurchaseOrderStatus.RECEIVED
    elif any(i.quantity_received > 0 for i in all_items):
        purchase_order.status = PurchaseOrderStatus.PARTIALLY_RECEIVED
    purchase_order.save(update_fields=["status"])

    return purchase_order


def cancel_order(*, purchase_order: PurchaseOrder, performed_by):
    if purchase_order.status in (PurchaseOrderStatus.RECEIVED, PurchaseOrderStatus.CANCELLED):
        raise InvalidTransitionError(f"Cannot cancel a {purchase_order.status} order.")
    purchase_order.status = PurchaseOrderStatus.CANCELLED
    purchase_order.save(update_fields=["status"])
    return purchase_order
