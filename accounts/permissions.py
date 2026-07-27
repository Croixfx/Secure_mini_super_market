"""
accounts/permissions.py

OWASP A01 - Broken Access Control.

These classes are the enforcement point, but they are NOT the only line of
defense — every ViewSet's get_queryset() must ALSO filter by branch/role.
Permission classes stop the wrong role from reaching a view; queryset
scoping stops the right role from reaching the wrong branch's data. You
need both; each catches what the other misses.
"""
from rest_framework.permissions import BasePermission

from .models import Role


class IsOwner(BasePermission):
    message = "Only an Owner account can perform this action."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == Role.OWNER)


class IsBranchManagerOrOwner(BasePermission):
    message = "Requires Branch Manager or Owner role."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in (Role.OWNER, Role.MANAGER)
        )


class IsSameBranchOrOwner(BasePermission):
    """
    Object-level check: an Owner may act on any branch's object; a Manager
    or Cashier may only act on objects belonging to their own branch.

    This is the check that directly defeats IDOR attempts like
    'GET /api/sales/482/' where sale 482 belongs to a different branch.
    """

    message = "You do not have access to this branch's data."

    def has_object_permission(self, request, view, obj):
        if request.user.role == Role.OWNER:
            return True
        obj_branch_id = getattr(obj, "branch_id", None)
        return obj_branch_id is not None and obj_branch_id == request.user.branch_id
