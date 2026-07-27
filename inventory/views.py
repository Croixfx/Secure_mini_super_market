"""
inventory/views.py

The queryset scoping here is the actual enforcement point for A01. The
permission classes decide WHO can reach the view; get_queryset() decides
WHAT they see once they're in it. Both are required — this file is the
first place that pattern gets exercised outside of accounts/.
"""
from rest_framework import viewsets, permissions as drf_permissions

from accounts.models import Role
from accounts.permissions import IsBranchManagerOrOwner, IsSameBranchOrOwner

from .models import Category, Product, Stock
from .serializers import CategorySerializer, ProductSerializer, StockSerializer


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
