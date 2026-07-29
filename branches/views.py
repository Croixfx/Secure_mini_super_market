"""
branches/views.py

Branch creation/editing is Owner-only — a Manager or Cashier has no
business reason to create a new branch or rename an existing one. This is
a stricter permission than most of the project's IsBranchManagerOrOwner
pattern, since branches themselves sit ABOVE the manager/branch
relationship, not within it.
"""
from rest_framework import viewsets, permissions as drf_permissions

from accounts.permissions import IsOwner

from .models import Branch
from .serializers import BranchSerializer


class BranchViewSet(viewsets.ModelViewSet):
    queryset = Branch.objects.all().order_by("name")
    serializer_class = BranchSerializer
    permission_classes = [drf_permissions.IsAuthenticated, IsOwner]
