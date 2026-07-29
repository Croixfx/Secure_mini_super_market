"""
sales/views.py

This is the view the entire stock ledger (inventory/services.py) was built
for — the first real caller of services.record_sale(). Everything here is
deliberately conservative:

- One DB transaction covers creating the Sale, all SaleItems, and every
  stock deduction — if any product is out of stock partway through a
  multi-item cart, the WHOLE sale rolls back, not just that line.
- Idempotency is checked FIRST, before any stock is touched, so a retried
  request (network blip, offline-sync replay) is a no-op that returns the
  original sale rather than a double sale.
- Prices are never read from the request — see serializers.py.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from rest_framework import permissions as drf_permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.models import Role
from accounts.permissions import IsBranchManagerOrOwner
from inventory.services import InsufficientStockError, record_sale

from . import refund_services
from .models import Sale, SaleItem
from .refund_serializers import RefundRequestSerializer, RefundSerializer
from .serializers import CheckoutSerializer, SaleSerializer


class CheckoutView(APIView):
    """
    A04 (Insecure Design): throttled at 30/min per cashier — see
    DEFAULT_THROTTLE_RATES["checkout"] in settings.py. This is a much
    higher ceiling than the 5/min login throttle deliberately: login is
    meant to be tight (5 wrong-password guesses is already suspicious),
    but checkout is a till in active, legitimate use — a fast cashier
    scanning a short cart and hitting pay can genuinely complete a sale
    every few seconds during a rush. 30/min (one every 2s) comfortably
    covers that real usage pattern while still bounding a compromised
    token or buggy client from hammering the stock ledger unboundedly.
    ScopedRateThrottle keys by authenticated user, so one busy till
    can't exhaust another cashier's allowance.
    """

    permission_classes = [drf_permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "checkout"

    @transaction.atomic
    def post(self, request):
        user = request.user
        if user.role == Role.OWNER:
            return Response(
                {"detail": "Owner accounts are not associated with a till branch for checkout."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Idempotency check FIRST — before touching stock at all. A resend
        # with the same key returns the original result, full stop.
        existing = Sale.objects.filter(idempotency_key=data["idempotency_key"]).first()
        if existing:
            return Response(SaleSerializer(existing).data, status=status.HTTP_200_OK)

        branch = user.branch

        # Server computes the total from CURRENT product prices — the
        # request only ever supplied product_id + quantity.
        line_items = []
        total = Decimal("0.00")
        for entry in data["items"]:
            product = entry["product"]
            quantity = entry["quantity"]
            unit_price = product.unit_price
            line_total = unit_price * quantity
            total += line_total
            line_items.append((product, quantity, unit_price, line_total))

        try:
            # Nested atomic() creates a SAVEPOINT. Without it, IntegrityError
            # here would mark the outer @transaction.atomic block as broken,
            # and the .get() below would raise TransactionManagementError
            # instead of returning the winner — only the savepoint needs to
            # roll back, not the whole request.
            with transaction.atomic():
                sale = Sale.objects.create(
                    branch=branch,
                    cashier=user,
                    idempotency_key=data["idempotency_key"],
                    payment_method=data["payment_method"],
                    total_amount=total,
                )
        except IntegrityError:
            # Race: two near-simultaneous requests with the same key. The
            # unique constraint on idempotency_key caught it — fetch and
            # return the winner rather than erroring the loser.
            sale = Sale.objects.get(idempotency_key=data["idempotency_key"])
            return Response(SaleSerializer(sale).data, status=status.HTTP_200_OK)

        try:
            for product, quantity, unit_price, line_total in line_items:
                SaleItem.objects.create(
                    sale=sale, product=product, quantity=quantity,
                    unit_price_at_sale=unit_price, line_total=line_total,
                )
                # The actual stock deduction — goes through the ledger,
                # never touches Stock.quantity directly. reference=sale
                # means every resulting StockMovement is traceable back to
                # this exact transaction.
                record_sale(product=product, branch=branch, quantity=quantity, performed_by=user, reference=sale)
        except InsufficientStockError as exc:
            # @transaction.atomic on the method rolls back the Sale and
            # every SaleItem created above — the cashier sees a clean
            # rejection, not a half-completed sale.
            transaction.set_rollback(True)
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(SaleSerializer(sale).data, status=status.HTTP_201_CREATED)


class SaleViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only sales history, branch-scoped like everything else."""

    serializer_class = SaleSerializer
    permission_classes = [drf_permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Sale.objects.select_related("branch", "cashier").prefetch_related("items__product")
        user = self.request.user
        if user.role == Role.OWNER:
            return qs
        return qs.filter(branch_id=user.branch_id)

    @action(
        detail=True, methods=["post"],
        permission_classes=[drf_permissions.IsAuthenticated, IsBranchManagerOrOwner],
    )
    def refund(self, request, pk=None):
        """
        POST /api/sales/history/<id>/refund/
        {"reason": "customer changed mind", "lines": [{"sale_item_id": 12, "quantity": 2, "restock": true}]}

        Manager/Owner only — deliberately NOT reachable by the cashier who
        made the original sale. A cashier processing their own refund with
        no oversight is a classic internal-fraud vector (ring up a fake
        return, pocket the cash) — this mirrors the same reasoning as
        wastage/stocktake being locked to management roles.
        """
        sale = self.get_object()  # get_queryset() already branch-scopes this
        serializer = RefundRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            refund_obj = refund_services.process_refund(
                sale=sale,
                lines=serializer.validated_data["lines"],
                reason=serializer.validated_data["reason"],
                performed_by=request.user,
            )
        except refund_services.RefundWindowExpiredError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(RefundSerializer(refund_obj).data, status=status.HTTP_201_CREATED)
