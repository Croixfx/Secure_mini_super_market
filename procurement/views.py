"""
procurement/views.py

Same branch-scoping pattern as inventory and sales: queryset filters by
branch for Manager/Cashier, Owner sees all. Suppliers are global (no
branch field), but still Manager/Owner only — a cashier has no business
reason to see supplier contact details or negotiated costs.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status, viewsets, permissions as drf_permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.models import Role
from accounts.permissions import IsBranchManagerOrOwner, IsSameBranchOrOwner

from . import services
from .models import PurchaseOrder, Supplier
from .serializers import (
    PurchaseOrderCreateSerializer,
    PurchaseOrderSerializer,
    ReceiveItemsSerializer,
    SupplierSerializer,
)


class SupplierViewSet(viewsets.ModelViewSet):
    queryset = Supplier.objects.filter(is_active=True).order_by("name")
    serializer_class = SupplierSerializer
    permission_classes = [drf_permissions.IsAuthenticated, IsBranchManagerOrOwner]


class PurchaseOrderViewSet(viewsets.ModelViewSet):
    serializer_class = PurchaseOrderSerializer
    permission_classes = [drf_permissions.IsAuthenticated, IsBranchManagerOrOwner, IsSameBranchOrOwner]

    def get_queryset(self):
        qs = PurchaseOrder.objects.select_related("supplier", "branch", "created_by").prefetch_related(
            "items__product"
        )
        user = self.request.user
        if user.role == Role.OWNER:
            return qs
        return qs.filter(branch_id=user.branch_id)

    def create(self, request, *args, **kwargs):
        """
        Overridden rather than using ModelSerializer's default create,
        because creating an order means creating its items in the same
        call — and branch/created_by must come from the authenticated
        user, never the request body.
        """
        user = request.user
        if user.role == Role.OWNER:
            return Response(
                {"detail": "Owner accounts must create orders on behalf of a specific branch — not yet supported from this endpoint."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = PurchaseOrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        po = PurchaseOrder.objects.create(
            supplier=serializer.validated_data["supplier"],
            branch=user.branch,
            created_by=user,
        )
        for item_data in serializer.validated_data["items"]:
            po.items.create(
                product=item_data["product"],
                quantity_ordered=item_data["quantity_ordered"],
                unit_cost=item_data["unit_cost"],
                batch_number=item_data.get("batch_number", ""),
                expiry_date=item_data.get("expiry_date"),
            )
        return Response(PurchaseOrderSerializer(po).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        po = self.get_object()
        try:
            services.send_order(purchase_order=po, performed_by=request.user)
        except (services.InvalidTransitionError, DjangoValidationError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PurchaseOrderSerializer(po).data)

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        po = self.get_object()
        serializer = ReceiveItemsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            services.receive_items(
                purchase_order=po,
                receipts=serializer.validated_data["receipts"],
                performed_by=request.user,
            )
        except (services.InvalidTransitionError, DjangoValidationError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        po.refresh_from_db()
        return Response(PurchaseOrderSerializer(po).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        po = self.get_object()
        try:
            services.cancel_order(purchase_order=po, performed_by=request.user)
        except services.InvalidTransitionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PurchaseOrderSerializer(po).data)
