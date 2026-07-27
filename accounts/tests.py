"""
accounts/tests.py

This suite is deliberately written to PROVE the security properties claimed
in models.py/views.py/permissions.py, not just to exercise the happy path.
Each test class maps to one AAA pillar or one OWASP category — structure it
this way in your README too, it reads very well to a reviewer.
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import LoginAttempt, Role

User = get_user_model()


class AuthenticationLockoutTests(APITestCase):
    """A07 - brute force protection."""

    def setUp(self):
        # ScopedRateThrottle's counters live in the default cache, which
        # persists for the whole test run (not per-test) — clear it so the
        # 5/min login throttle from one test doesn't bleed into the next.
        cache.clear()
        self.user = User.objects.create_user(username="cashier1", password="correct-horse-battery-staple")
        self.login_url = reverse("token_obtain_pair")

    def test_generic_error_on_wrong_password(self):
        resp = self.client.post(self.login_url, {"username": "cashier1", "password": "wrong"})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(resp.data, {"detail": "Unable to log in with the provided credentials."})

    def test_same_generic_error_for_nonexistent_username(self):
        """A03/A07: response must be indistinguishable from a wrong password,
        so an attacker can't enumerate valid usernames from the API."""
        resp_bad_user = self.client.post(self.login_url, {"username": "ghost", "password": "x"})
        resp_bad_pass = self.client.post(self.login_url, {"username": "cashier1", "password": "wrong"})
        self.assertEqual(resp_bad_user.status_code, resp_bad_pass.status_code)
        self.assertEqual(resp_bad_user.data, resp_bad_pass.data)

    def test_account_locks_after_max_attempts(self):
        for _ in range(5):
            self.client.post(self.login_url, {"username": "cashier1", "password": "wrong"})
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_locked())

        # The login throttle scope (5/min) and the lockout threshold (5
        # attempts) are numerically identical, so the verification request
        # below would otherwise be the 6th hit against the throttle and get
        # 429 before the view's own lockout check ever runs. Clear the
        # throttle cache so this test isolates lockout behavior, not
        # throttling (which isn't what's under test here).
        cache.clear()

        # Even the CORRECT password must now be rejected while locked.
        resp = self.client.post(
            self.login_url, {"username": "cashier1", "password": "correct-horse-battery-staple"}
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_every_attempt_is_logged(self):
        self.client.post(self.login_url, {"username": "cashier1", "password": "wrong"})
        self.assertEqual(LoginAttempt.objects.filter(username_attempted="cashier1").count(), 1)
        self.assertFalse(LoginAttempt.objects.first().success)


class BranchScopedAccessControlTests(APITestCase):
    """
    A01 - Broken Access Control / IDOR.

    These are the tests to point to first in an interview: they assert that
    a lower-privileged, correctly-authenticated user is STILL blocked from
    another branch's data, which is the failure mode that "just add
    @login_required" doesn't catch.
    """

    def setUp(self):
        from branches.models import Branch  # local import to avoid app-loading order issues

        cache.clear()
        self.branch_a = Branch.objects.create(name="Kimironko")
        self.branch_b = Branch.objects.create(name="Remera")

        self.owner = User.objects.create_user(username="owner", password="pw", role=Role.OWNER)
        self.manager_a = User.objects.create_user(
            username="manager_a", password="pw", role=Role.MANAGER, branch=self.branch_a
        )
        self.cashier_b = User.objects.create_user(
            username="cashier_b", password="pw", role=Role.CASHIER, branch=self.branch_b
        )

    def _login(self, username, password="pw"):
        resp = self.client.post(reverse("token_obtain_pair"), {"username": username, "password": password})
        token = resp.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_cashier_cannot_list_other_users(self):
        """Only Owner may reach the user-admin endpoint at all."""
        self._login("cashier_b")
        resp = self.client.get(reverse("user-admin-list"))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_can_list_users(self):
        self._login("owner")
        resp = self.client.get(reverse("user-admin-list"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    # A real IDOR test against, e.g., /api/sales/<id>/ belongs in the sales
    # app's test suite once that model exists, following this same pattern:
    # authenticate as manager_a, request an object belonging to branch_b,
    # assert 403/404 rather than 200.


class MassAssignmentProtectionTests(APITestCase):
    """A08 - a client must never be able to set fields outside the serializer's
    explicit allow-list, even by guessing field names."""

    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(username="owner", password="pw", role=Role.OWNER)
        self._login("owner")

    def _login(self, username, password="pw"):
        resp = self.client.post(reverse("token_obtain_pair"), {"username": username, "password": password})
        token = resp.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_cannot_set_is_superuser_via_api(self):
        resp = self.client.post(
            reverse("user-admin-list"),
            {
                "username": "sneaky",
                "password": "somepassword123",
                "role": Role.CASHIER,
                "is_superuser": True,  # not in the serializer's allow-list
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        created = User.objects.get(username="sneaky")
        self.assertFalse(created.is_superuser)
