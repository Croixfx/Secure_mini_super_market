"""
inventory/transfer_services.py

New file, drops into inventory/ as-is.

This is the first real caller of transfer_out()/transfer_in() - both
existed in services.py since the stock ledger feature, unused until now.

Two-party enforcement: dispatching requires being at the SOURCE branch;
receiving requires being at the DESTINATION branch. This is checked here
in the service layer AND should be checked again at the view/permission
layer (defense in depth, same as everywhere else in this project) - the
service layer raises PermissionError-style exceptions rather than DRF
exceptions, since services.py has no framework dependency, matching the
existing style of inventory/services.py.
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import Role

from .models import StockTransfer, TransferStatus
from .services import InsufficientStockError, transfer_in, transfer_out


class TransferPermissionError(Exception):
    """Raised when a user tries to dispatch/receive a transfer that isn't theirs to act on."""


class InvalidTransferTransitionError(Exception):
    """Raised on an illegal status transition (e.g. receiving a REQUESTED transfer)."""


def request_transfer(*, product, from_branch, to_branch, quantity, requested_by):
    if from_branch == to_branch:
        raise ValidationError("Cannot transfer stock to the same branch.")
    if quantity <= 0:
        raise ValidationError("Transfer quantity must be positive.")
    return StockTransfer.objects.create(
        product=product, from_branch=from_branch, to_branch=to_branch,
        quantity_requested=quantity, requested_by=requested_by,
    )


def _user_belongs_to_branch(user, branch):
    return user.role == Role.OWNER or user.branch_id == branch.id


@transaction.atomic
def dispatch_transfer(*, stock_transfer: StockTransfer, performed_by):
    """
    Marks a transfer as physically sent - the ONE point where stock
    actually leaves the source branch's ledger. Only someone at the
    source branch (or the Owner) can do this, since they're the one
    physically responsible for what leaves their shelf.
    """
    if not _user_belongs_to_branch(performed_by, stock_transfer.from_branch):
        raise TransferPermissionError("Only the source branch can dispatch this transfer.")
    if stock_transfer.status != TransferStatus.REQUESTED:
        raise InvalidTransferTransitionError(
            f"Cannot dispatch a transfer that is {stock_transfer.status} (must be REQUESTED)."
        )

    # This is where InsufficientStockError can genuinely surface - the
    # source branch may not actually have enough stock to fulfill the
    # request, and that's discovered HERE, not at request time, since
    # requesting is just a record and dispatching is the real commitment.
    transfer_out(
        product=stock_transfer.product, branch=stock_transfer.from_branch,
        quantity=stock_transfer.quantity_requested, performed_by=performed_by, reference=stock_transfer,
    )
    stock_transfer.status = TransferStatus.IN_TRANSIT
    stock_transfer.dispatched_by = performed_by
    stock_transfer.dispatched_at = timezone.now()
    stock_transfer.save(update_fields=["status", "dispatched_by", "dispatched_at"])
    return stock_transfer


@transaction.atomic
def receive_transfer(*, stock_transfer: StockTransfer, quantity_received: int, performed_by):
    """
    Confirms what actually arrived - may be less than what was dispatched.
    Only someone at the destination branch (or the Owner) can confirm
    this, since they're the one physically counting what showed up.
    """
    if not _user_belongs_to_branch(performed_by, stock_transfer.to_branch):
        raise TransferPermissionError("Only the destination branch can receive this transfer.")
    if stock_transfer.status != TransferStatus.IN_TRANSIT:
        raise InvalidTransferTransitionError(
            f"Cannot receive a transfer that is {stock_transfer.status} (must be IN_TRANSIT)."
        )
    if quantity_received < 0 or quantity_received > stock_transfer.quantity_requested:
        raise ValidationError(
            f"Received quantity must be between 0 and {stock_transfer.quantity_requested} (what was dispatched)."
        )

    if quantity_received > 0:
        transfer_in(
            product=stock_transfer.product, branch=stock_transfer.to_branch,
            quantity=quantity_received, performed_by=performed_by, reference=stock_transfer,
        )
    stock_transfer.status = TransferStatus.RECEIVED
    stock_transfer.quantity_received = quantity_received
    stock_transfer.received_by = performed_by
    stock_transfer.received_at = timezone.now()
    stock_transfer.save(update_fields=["status", "quantity_received", "received_by", "received_at"])
    return stock_transfer


def cancel_transfer(*, stock_transfer: StockTransfer, performed_by):
    """
    Only possible before dispatch - once stock has actually left the
    source branch's ledger (IN_TRANSIT), cancelling would require its own
    reversal movement, which is a deliberate known gap, not built here.
    """
    if stock_transfer.status != TransferStatus.REQUESTED:
        raise InvalidTransferTransitionError(
            f"Cannot cancel a transfer that is already {stock_transfer.status} - "
            f"once dispatched, stock has already left the source branch."
        )
    stock_transfer.status = TransferStatus.CANCELLED
    stock_transfer.save(update_fields=["status"])
    return stock_transfer
