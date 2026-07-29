"""
branches/views.py

Branch creation/editing is Owner-only — a Manager or Cashier has no
business reason to create a new branch or rename an existing one. This is
a stricter permission than most of the project's IsBranchManagerOrOwner
pattern, since branches themselves sit ABOVE the manager/branch
relationship, not within it. list/retrieve are Owner-only too — see
tests_management.py: test_manager_cannot_even_list_branches_via_this_endpoint
— since the full BranchSerializer exposes address/phone/staff_count,
which are legitimately operational detail, not something every role
needs.

`lookup` is a deliberate, narrow exception to that: a Manager requesting a
stock transfer (inventory/transfer_views.py) needs to know OTHER branches
exist by name to pick a destination — that's a real requirement the
transfer feature surfaced, not a reason to loosen the list/retrieve
lockdown above. It returns id+name only, nothing else on the model.
"""
from rest_framework import viewsets, permissions as drf_permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.permissions import IsBranchManagerOrOwner, IsOwner

from .models import Branch
from .serializers import BranchLookupSerializer, BranchSerializer


class BranchViewSet(viewsets.ModelViewSet):
    queryset = Branch.objects.all().order_by("name")
    serializer_class = BranchSerializer
    permission_classes = [drf_permissions.IsAuthenticated, IsOwner]

    @action(detail=False, methods=["get"], permission_classes=[drf_permissions.IsAuthenticated, IsBranchManagerOrOwner])
    def lookup(self, request):
        branches = Branch.objects.all().order_by("name")
        return Response(BranchLookupSerializer(branches, many=True).data)
