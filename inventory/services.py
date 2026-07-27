"""
inventory/services.py

This module is the ONLY place allowed to change Stock.quantity. Views,
other apps (sales, procurement, transfers), and management commands must
call apply_movement() rather than touching Stock objects directly — that's
what guarantees the ledger and the cached quantity can never drift apart.

If a future developer (including future-you) is tempted to do
`stock.quantity += 5; stock.save()` somewhere else in the codebase, that's
the bug this module exists to prevent. Enforce it in code review / a
lightweight test that greps for direct `.quantity =` assignments outside
this file, if you want to make the rule unbreakable rather than just
documented.
"""
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import MovementType, Stock, StockMovement


class InsufficientStockError(Exception):
    """Raised when a movement would take stock negative (e.g. selling more
    than is on hand). Deliberately a distinct exception from ValidationError
    so callers (POS checkout) can catch it specifically and show
    "out of stock" rather than a generic error."""


@transaction.atomic
def apply_movement(
    *,
    product,
    branch,
    movement_type: str,
    quantity_delta: int,
    performed_by,
    reference=None,
    batch_number: str = "",
    expiry_date=None,
    unit_cost=None,
    reason: str = "",
    allow_negative: bool = False,
) -> StockMovement:
    """
    The single write path for every stock change in the system.

    1. Locks the Stock row (select_for_update) so two concurrent movements
       against the same product/branch can't race and corrupt the cached
       quantity — this matters most for SALE movements, where two tills at
       the same branch could otherwise both read "3 left" and both sell,
       taking it to -1 without this lock.
    2. Validates the resulting quantity won't go negative, unless the
       caller explicitly allows it (STOCKTAKE_ADJUSTMENT can legitimately
       correct a quantity that was wrongly allowed to go negative before
       this system existed, so it's the one caller allowed to opt out).
    3. Writes the StockMovement row FIRST, so the ledger always has an
       entry even if something later fails — the movement is the fact,
       the cache update is a derived side effect of that fact.
    4. Updates (or creates) the Stock cache row.
    """
    stock, _ = Stock.objects.select_for_update().get_or_create(
        product=product, branch=branch, defaults={"quantity": 0}
    )

    resulting_quantity = stock.quantity + quantity_delta
    if resulting_quantity < 0 and not allow_negative:
        raise InsufficientStockError(
            f"Movement would take {product.sku} @ {branch} to {resulting_quantity} "
            f"(current: {stock.quantity}, requested change: {quantity_delta})"
        )

    reference_ct = ContentType.objects.get_for_model(reference) if reference else None
    reference_id = reference.pk if reference else None

    movement = StockMovement.objects.create(
        product=product,
        branch=branch,
        movement_type=movement_type,
        quantity_delta=quantity_delta,
        batch_number=batch_number,
        expiry_date=expiry_date,
        unit_cost=unit_cost,
        reason=reason,
        reference_content_type=reference_ct,
        reference_object_id=reference_id,
        performed_by=performed_by,
    )

    stock.quantity = max(resulting_quantity, 0) if allow_negative and resulting_quantity < 0 else resulting_quantity
    stock.save(update_fields=["quantity", "updated_at"])

    return movement


# --- Convenience wrappers for each movement type, so callers don't have to
# remember the right sign or movement_type string. These are what
# procurement/, sales/, and transfers/ apps should actually call. ---

def receive_stock(*, product, branch, quantity, performed_by, batch_number="", expiry_date=None,
                   unit_cost=None, reference=None):
    if quantity <= 0:
        raise ValidationError("Received quantity must be positive.")
    return apply_movement(
        product=product, branch=branch, movement_type=MovementType.RECEIPT,
        quantity_delta=quantity, performed_by=performed_by, batch_number=batch_number,
        expiry_date=expiry_date, unit_cost=unit_cost, reference=reference,
    )


def record_sale(*, product, branch, quantity, performed_by, reference=None):
    if quantity <= 0:
        raise ValidationError("Sale quantity must be positive.")
    return apply_movement(
        product=product, branch=branch, movement_type=MovementType.SALE,
        quantity_delta=-quantity, performed_by=performed_by, reference=reference,
    )


def record_return(*, product, branch, quantity, performed_by, reference=None, reason=""):
    if quantity <= 0:
        raise ValidationError("Return quantity must be positive.")
    return apply_movement(
        product=product, branch=branch, movement_type=MovementType.RETURN,
        quantity_delta=quantity, performed_by=performed_by, reference=reference, reason=reason,
    )


def record_wastage(*, product, branch, quantity, performed_by, reason, reference=None):
    if quantity <= 0:
        raise ValidationError("Wastage quantity must be positive.")
    if not reason:
        raise ValidationError("Wastage must always have a reason — this is a shrinkage report input.")
    return apply_movement(
        product=product, branch=branch, movement_type=MovementType.WASTAGE,
        quantity_delta=-quantity, performed_by=performed_by, reason=reason, reference=reference,
    )


def transfer_out(*, product, branch, quantity, performed_by, reference=None):
    """Called when a transfer is REQUESTED, reserving stock at the source
    branch. Pairs with transfer_in(), called when the destination confirms
    receipt — mirroring the requested -> in_transit -> received flow."""
    if quantity <= 0:
        raise ValidationError("Transfer quantity must be positive.")
    return apply_movement(
        product=product, branch=branch, movement_type=MovementType.TRANSFER_OUT,
        quantity_delta=-quantity, performed_by=performed_by, reference=reference,
    )


def transfer_in(*, product, branch, quantity, performed_by, reference=None, batch_number="", expiry_date=None):
    if quantity <= 0:
        raise ValidationError("Transfer quantity must be positive.")
    return apply_movement(
        product=product, branch=branch, movement_type=MovementType.TRANSFER_IN,
        quantity_delta=quantity, performed_by=performed_by, reference=reference,
        batch_number=batch_number, expiry_date=expiry_date,
    )


def record_stocktake_adjustment(*, product, branch, counted_quantity, performed_by, reason=""):
    """
    Reconciles the system's cached quantity against a real physical count.
    The delta is computed HERE (counted - current), and it can be negative
    or positive — this is the one caller that passes allow_negative=True,
    because the whole point of a stocktake is correcting drift that may
    already be wrong in either direction.
    """
    stock = Stock.objects.filter(product=product, branch=branch).first()
    current = stock.quantity if stock else 0
    delta = counted_quantity - current
    if delta == 0:
        return None  # no discrepancy — nothing to log
    return apply_movement(
        product=product, branch=branch, movement_type=MovementType.STOCKTAKE_ADJUSTMENT,
        quantity_delta=delta, performed_by=performed_by,
        reason=reason or f"Stocktake correction: system had {current}, counted {counted_quantity}",
        allow_negative=True,
    )
