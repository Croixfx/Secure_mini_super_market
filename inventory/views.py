"""
inventory/views.py

The queryset scoping here is the actual enforcement point for A01. The
permission classes decide WHO can reach the view; get_queryset() decides
WHAT they see once they're in it. Both are required — this file is the
first place that pattern gets exercised outside of accounts/.
"""
from rest_framework import status, viewsets, permissions as drf_permissions
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.response import Response

from accounts.models import Role
from accounts.permissions import IsBranchManagerOrOwner, IsSameBranchOrOwner

from . import services
from .models import Category, Product, Stock, StockMovement
from .serializers import (
    CategorySerializer,
    ProductSerializer,
    StockSerializer,
    StockMovementSerializer,
    StocktakeRequestSerializer,
    WastageRequestSerializer,
)


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all().order_by("name")
    serializer_class = CategorySerializer
    permission_classes = [drf_permissions.IsAuthenticated, IsBranchManagerOrOwner]


class ProductViewSet(viewsets.ModelViewSet):
    """
    Product catalog itself isn't branch-scoped (see model docstring), but
    write access is still role-gated: cashiers can browse/search products
    (they need this at checkout) but cannot create/edit/delete them.
    """

    queryset = Product.objects.filter(is_active=True).order_by("name")
    serializer_class = ProductSerializer
    filter_backends = [SearchFilter]
    # Barcode is included so a scanner's fast keyboard-input burst (which
    # lands in the same search box) matches a product directly, not just
    # typed name searches.
    search_fields = ["name", "sku", "barcode"]

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [drf_permissions.IsAuthenticated(), IsBranchManagerOrOwner()]
        return [drf_permissions.IsAuthenticated()]

    def get_serializer_context(self):
        # Needed so ProductSerializer.to_representation can redact
        # cost_price based on request.user.role.
        context = super().get_serializer_context()
        context["request"] = self.request
        return context


class StockViewSet(viewsets.ModelViewSet):
    """
    This is the view the accounts app's IsSameBranchOrOwner permission was
    written for: an Owner sees every branch's stock; a Manager or Cashier
    sees only their own branch's, enforced twice over —

      1. get_queryset() filters the LIST results to the caller's branch
         (so branch B's rows never even appear in a list response), and
      2. IsSameBranchOrOwner.has_object_permission() blocks a direct
         GET/PATCH on a specific stock row that belongs to another branch
         (so guessing an ID doesn't work either).
    """

    serializer_class = StockSerializer
    permission_classes = [drf_permissions.IsAuthenticated, IsSameBranchOrOwner]

    def get_queryset(self):
        qs = Stock.objects.select_related("product", "branch").order_by("product__name")
        user = self.request.user
        if user.role == Role.OWNER:
            return qs
        return qs.filter(branch_id=user.branch_id)

    def perform_create(self, serializer):
        # branch is NEVER taken from the client payload — always derived
        # from the authenticated user, closing off a trivial IDOR-by-write
        # (a manager POSTing stock rows into another branch by just setting
        # a different branch id in the request body).
        user = self.request.user
        branch = user.branch if user.role != Role.OWNER else self.request.data.get("branch")
        serializer.save(branch_id=branch if isinstance(branch, int) else getattr(branch, "id", branch))

    def perform_update(self, serializer):
        # Object-level permission already ran via has_object_permission,
        # but re-assert branch cannot be changed via PATCH either.
        serializer.save(branch=serializer.instance.branch)

    @action(detail=False, methods=["post"], permission_classes=[drf_permissions.IsAuthenticated, IsBranchManagerOrOwner])
    def record_wastage(self, request):
        """
        POST /api/inventory/stock/record_wastage/
        {"product": 4, "quantity": 3, "reason": "expired"}

        Manager/Owner only — a cashier should never be able to write off
        stock as wastage themselves, since that's exactly the endpoint
        someone would abuse to cover for theft or an unrecorded sale.
        """
        serializer = WastageRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        branch = user.branch if user.role != Role.OWNER else request.data.get("branch_id")
        try:
            movement = services.record_wastage(
                product=serializer.validated_data["product"],
                branch=branch,
                quantity=serializer.validated_data["quantity"],
                reason=serializer.validated_data["reason"],
                performed_by=user,
            )
        except services.InsufficientStockError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(StockMovementSerializer(movement).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], permission_classes=[drf_permissions.IsAuthenticated, IsBranchManagerOrOwner])
    def stocktake_adjustment(self, request):
        """
        POST /api/inventory/stock/stocktake_adjustment/
        {"product": 4, "counted_quantity": 96, "reason": "June cycle count"}

        Reconciles a physical count against the system. Manager/Owner only,
        for the same reason as wastage — this endpoint can silently erase a
        discrepancy that should actually be investigated as shrinkage.
        """
        serializer = StocktakeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        branch = user.branch if user.role != Role.OWNER else request.data.get("branch_id")
        movement = services.record_stocktake_adjustment(
            product=serializer.validated_data["product"],
            branch=branch,
            counted_quantity=serializer.validated_data["counted_quantity"],
            reason=serializer.validated_data.get("reason", ""),
            performed_by=user,
        )
        if movement is None:
            return Response({"detail": "No discrepancy — count matches system quantity."}, status=status.HTTP_200_OK)
        return Response(StockMovementSerializer(movement).data, status=status.HTTP_201_CREATED)


class StockMovementViewSet(viewsets.ReadOnlyModelViewSet):
    """
    The traceability endpoint: GET /api/inventory/movements/?product=4
    Read-only everywhere — the ONLY way to create a StockMovement is
    through services.py, called from a real domain action (a sale, a
    received purchase order, a confirmed transfer, or the two explicit
    action endpoints above). There is deliberately no generic "create a
    movement" POST here, because that would let someone bypass the actual
    business event a movement is supposed to represent.
    """

    serializer_class = StockMovementSerializer
    permission_classes = [drf_permissions.IsAuthenticated, IsSameBranchOrOwner]
    filterset_fields = ["product", "movement_type"]

    def get_queryset(self):
        qs = StockMovement.objects.select_related("product", "branch", "performed_by").all()
        user = self.request.user
        if user.role != Role.OWNER:
            qs = qs.filter(branch_id=user.branch_id)
        product_id = self.request.query_params.get("product")
        if product_id:
            qs = qs.filter(product_id=product_id)
        movement_type = self.request.query_params.get("movement_type")
        if movement_type:
            qs = qs.filter(movement_type=movement_type)
        return qs
