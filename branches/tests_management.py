"""
branches/tests_management.py

Named separately from the existing branches/tests.py (if one exists from
earlier sessions) to avoid clobbering it — Claude Code should merge this
in as an additional test file, not overwrite anything already there.
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role

from .models import Branch

User = get_user_model()


class BranchManagementAccessControlTests(APITestCase):
    def setUp(self):
        # ScopedRateThrottle's counters live in the default cache, which
        # persists for the whole test run (not per-test) — clear it so the
        # 5/min login throttle from an earlier test/file doesn't 429 this
        # one's login call. Same fix as every other tests.py in the project
        # (accounts, sales, inventory, procurement).
        cache.clear()
        self.branch = Branch.objects.create(name="Kimironko")
        self.owner = User.objects.create_user(username="owner1", password="pw", role=Role.OWNER)
        self.manager = User.objects.create_user(
            username="manager1", password="pw", role=Role.MANAGER, branch=self.branch
        )

    def _login(self, username):
        resp = self.client.post(reverse("token_obtain_pair"), {"username": username, "password": "pw"})
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_owner_can_create_branch(self):
        self._login("owner1")
        resp = self.client.post(reverse("branch-list"), {"name": "Remera", "address": "KG 11 Ave", "phone": "0788000000"})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_manager_cannot_create_branch(self):
        self._login("manager1")
        resp = self.client.post(reverse("branch-list"), {"name": "Remera"})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_cannot_even_list_branches_via_this_endpoint(self):
        """Owner-only means owner-only for read too — a manager already
        gets their own branch context from their JWT/user record, not
        this cross-branch management endpoint."""
        self._login("manager1")
        resp = self.client.get(reverse("branch-list"))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_count_reflects_real_assignment(self):
        self._login("owner1")
        resp = self.client.get(reverse("branch-detail", args=[self.branch.id]))
        self.assertEqual(resp.data["staff_count"], 1)  # just the manager so far

    def test_manager_can_use_lookup_but_gets_id_and_name_only(self):
        """The narrow exception to the list lockdown above — a Manager
        requesting a stock transfer needs to see other branches exist by
        name, but not the Owner-only operational detail."""
        Branch.objects.create(name="Remera")
        self._login("manager1")
        resp = self.client.get(reverse("branch-lookup"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 2)
        self.assertEqual(set(resp.data[0].keys()), {"id", "name"})

    def test_cashier_cannot_use_branch_lookup_either(self):
        User.objects.create_user(username="cashier1", password="pw", role=Role.CASHIER, branch=self.branch)
        self._login("cashier1")
        resp = self.client.get(reverse("branch-lookup"))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
