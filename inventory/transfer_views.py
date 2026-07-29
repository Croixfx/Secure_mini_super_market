"""
inventory/transfer_views.py

New file, drops into inventory/ as-is. Register its viewset in
inventory/urls.py (see wiring doc).
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import status, viewsets, permissions as drf_permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.models import Role
from accounts.permissions import IsBranchManagerOrOwner

from . import transfer_services
from .models import StockTransfer
from .transfer_serializers import ReceiveTransferSerializer, StockTransferSerializer, TransferCreateSerializer


class StockTransferViewSet(viewsets.ModelViewSet):
    serializer_class = StockTransferSerializer
    permission_classes = [drf_permissions.IsAuthenticated, IsBranchManagerOrOwner]

    def get_queryset(self):
        qs = StockTransfer.objects.select_related(
            "product", "from_branch", "to_branch", "requested_by"
        )
        user = self.request.user
        if user.role == Role.OWNER:
            return qs
        # A manager sees transfers where THEIR branch is on either side -
        # they need visibility into stock leaving as much as stock arriving.
        return qs.filter(Q(from_branch_id=user.branch_id) | Q(to_branch_id=user.branch_id))

    def create(self, request, *args, **kwargs):
        user = request.user
        serializer = TransferCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Defense in depth: a manager can only REQUEST a transfer touching
        # their own branch (either side) - can't create a transfer between
        # two branches they have nothing to do with.
        if user.role != Role.OWNER:
            if user.branch_id not in (data["from_branch"].id, data["to_branch"].id):
                return Response(
                    {"detail": "You can only request transfers involving your own branch."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        try:
            transfer = transfer_services.request_transfer(
                product=data["product"], from_branch=data["from_branch"], to_branch=data["to_branch"],
                quantity=data["quantity"], requested_by=user,
            )
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(StockTransferSerializer(transfer).data, status=status.HTTP_201_CREATED)

    # Named dispatch_transfer, not dispatch — django.views.generic.base.View
    # already defines dispatch() as the method that routes every incoming
    # request (runs authentication, permission checks, then calls
    # get/post/etc.). Naming this method `dispatch` overrides that for the
    # WHOLE viewset, not just this action — every request, including plain
    # list/create, would skip real request initialization and see
    # request.user as AnonymousUser. Confirmed by running the tests with
    # the original name: all 12 transfer tests failed with
    # `AttributeError: 'AnonymousUser' object has no attribute 'role'`
    # inside get_queryset(), not just the dispatch action. url_path/url_name
    # keep the public URL and reverse name identical (.../dispatch/,
    # stocktransfer-dispatch) so nothing external needs to change.
    @action(detail=True, methods=["post"], url_path="dispatch", url_name="dispatch")
    def dispatch_transfer(self, request, pk=None):
        stock_transfer = self.get_object()
        try:
            transfer_services.dispatch_transfer(stock_transfer=stock_transfer, performed_by=request.user)
        except transfer_services.TransferPermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except (transfer_services.InvalidTransferTransitionError, DjangoValidationError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except transfer_services.InsufficientStockError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(StockTransferSerializer(stock_transfer).data)

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        stock_transfer = self.get_object()
        serializer = ReceiveTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            transfer_services.receive_transfer(
                stock_transfer=stock_transfer,
                quantity_received=serializer.validated_data["quantity_received"],
                performed_by=request.user,
            )
        except transfer_services.TransferPermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except (transfer_services.InvalidTransferTransitionError, DjangoValidationError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(StockTransferSerializer(stock_transfer).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        stock_transfer = self.get_object()
        try:
            transfer_services.cancel_transfer(stock_transfer=stock_transfer, performed_by=request.user)
        except transfer_services.InvalidTransferTransitionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(StockTransferSerializer(stock_transfer).data)
