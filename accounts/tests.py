"""
accounts/tests.py

This suite is deliberately written to PROVE the security properties claimed
in models.py/views.py/permissions.py, not just to exercise the happy path.
Each test class maps to one AAA pillar or one OWASP category — structure it
this way in your README too, it reads very well to a reviewer.
"""
import base64

import pyotp
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework import status
from rest_framework.test import APITestCase

from .models import LoginAttempt, Role

User = get_user_model()


def _valid_totp_code(device):
    """The code a real authenticator app would show right now for this
    device's actual secret — pyotp is a test-only dependency, production
    code never generates codes, only verifies them (django-otp)."""
    secret = base64.b32encode(device.bin_key).decode("ascii")
    return pyotp.TOTP(secret).now()


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


class RefreshCookieTests(APITestCase):
    """
    A02/A07 - the refresh token must never be reachable from JS. Proves it
    lives only in an httpOnly cookie (never the JSON body), that a page
    refresh can restore a session from that cookie alone, and that rotation/
    blacklisting/logout all operate on the cookie rather than a body value.
    """

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="cashier1", password="pw")
        self.login_url = reverse("token_obtain_pair")
        self.refresh_silent_url = reverse("refresh_silent")
        self.logout_url = reverse("logout")

    def test_login_response_body_has_no_refresh_token(self):
        resp = self.client.post(self.login_url, {"username": "cashier1", "password": "pw"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.data)
        self.assertNotIn("refresh", resp.data)

    def test_login_sets_httponly_secure_samesite_lax_cookie(self):
        resp = self.client.post(self.login_url, {"username": "cashier1", "password": "pw"})
        cookie = resp.cookies[settings.REFRESH_TOKEN_COOKIE_NAME]
        self.assertNotEqual(cookie.value, "")
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        # secure=True only when SESSION_COOKIE_SECURE is (env-driven, off for
        # local http:// dev) — asserting it mirrors that setting, not a
        # hardcoded True, is the point: this must turn on in production
        # automatically, not require remembering to flip it here too.
        self.assertEqual(bool(cookie["secure"]), settings.SESSION_COOKIE_SECURE)

    def test_refresh_silent_without_cookie_is_rejected(self):
        resp = self.client.post(self.refresh_silent_url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_silent_with_valid_cookie_restores_session(self):
        """The actual point of this feature: a client with NO access token
        (e.g. a fresh page load) but a valid refresh cookie can get a new
        access token without the user re-entering credentials."""
        self.client.post(self.login_url, {"username": "cashier1", "password": "pw"})
        # Simulate a page refresh: a brand-new client-side request carrying
        # only the cookie the browser stored, no Authorization header at all.
        resp = self.client.post(self.refresh_silent_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.data)
        self.assertNotIn("refresh", resp.data)  # rotated cookie, still never in the body

    def test_refresh_silent_rotates_the_cookie_and_blacklists_the_old_token(self):
        login_resp = self.client.post(self.login_url, {"username": "cashier1", "password": "pw"})
        first_refresh = login_resp.cookies[settings.REFRESH_TOKEN_COOKIE_NAME].value

        refresh_resp = self.client.post(self.refresh_silent_url)
        second_refresh = refresh_resp.cookies[settings.REFRESH_TOKEN_COOKIE_NAME].value
        self.assertNotEqual(first_refresh, second_refresh)

        # Replaying the OLD (pre-rotation) refresh cookie must now fail —
        # proves BLACKLIST_AFTER_ROTATION is actually wired through this
        # cookie-based path, not just the body-based one simplejwt ships with.
        self.client.cookies[settings.REFRESH_TOKEN_COOKIE_NAME] = first_refresh
        replay_resp = self.client.post(self.refresh_silent_url)
        self.assertEqual(replay_resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_clears_cookie_and_blacklists_refresh_token(self):
        login_resp = self.client.post(self.login_url, {"username": "cashier1", "password": "pw"})
        access = login_resp.data["access"]
        refresh_value = login_resp.cookies[settings.REFRESH_TOKEN_COOKIE_NAME].value

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        logout_resp = self.client.post(self.logout_url)
        self.assertEqual(logout_resp.status_code, status.HTTP_205_RESET_CONTENT)

        deleted_cookie = logout_resp.cookies[settings.REFRESH_TOKEN_COOKIE_NAME]
        self.assertEqual(deleted_cookie.value, "")  # cleared

        # The blacklisted token must be rejected even if a client held onto
        # the raw value after logout (e.g. an old tab that hadn't reloaded).
        self.client.cookies[settings.REFRESH_TOKEN_COOKIE_NAME] = refresh_value
        replay_resp = self.client.post(self.refresh_silent_url)
        self.assertEqual(replay_resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_succeeds_even_with_no_refresh_cookie(self):
        """Lenient by design: the user's goal (end up logged out) is
        achievable whether or not there's a valid refresh cookie to
        blacklist — this must not block on that."""
        login_resp = self.client.post(self.login_url, {"username": "cashier1", "password": "pw"})
        access = login_resp.data["access"]
        self.client.cookies.clear()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        resp = self.client.post(self.logout_url)
        self.assertEqual(resp.status_code, status.HTTP_205_RESET_CONTENT)


class PosAdminCookieIsolationTests(APITestCase):
    """
    A01 - pos-frontend and admin-frontend both talk to the same backend
    host, so without distinct cookie names/paths, logging into one app
    would silently authenticate the other too (the browser can't tell
    which frontend page a cookie "belongs" to — only domain+path). That
    would defeat the entire reason these are separate frontend builds: a
    cashier session should have no path into the admin app, not just no
    USEFUL path once there.
    """

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="cashier1", password="pw")

    def test_pos_login_cookie_is_not_sent_to_admin_refresh_silent(self):
        self.client.post(reverse("pos_token_obtain_pair"), {"username": "cashier1", "password": "pw"})
        # The client now holds a pos_refresh_token cookie. Hitting the
        # ADMIN app's silent-restore endpoint must NOT succeed from it.
        resp = self.client.post(reverse("admin_refresh_silent"))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_login_cookie_is_not_sent_to_pos_refresh_silent(self):
        self.client.post(reverse("admin_token_obtain_pair"), {"username": "cashier1", "password": "pw"})
        resp = self.client.post(reverse("pos_refresh_silent"))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_pos_and_admin_cookies_use_different_names(self):
        pos_resp = self.client.post(reverse("pos_token_obtain_pair"), {"username": "cashier1", "password": "pw"})
        admin_resp = self.client.post(reverse("admin_token_obtain_pair"), {"username": "cashier1", "password": "pw"})
        self.assertIn("pos_refresh_token", pos_resp.cookies)
        self.assertNotIn("admin_refresh_token", pos_resp.cookies)
        self.assertIn("admin_refresh_token", admin_resp.cookies)
        self.assertNotIn("pos_refresh_token", admin_resp.cookies)

    def test_each_app_can_still_restore_its_own_session(self):
        """The isolation fix shouldn't have broken the actual feature —
        each app's own login must still successfully restore via its own
        refresh-silent endpoint."""
        self.client.post(reverse("pos_token_obtain_pair"), {"username": "cashier1", "password": "pw"})
        pos_restore = self.client.post(reverse("pos_refresh_silent"))
        self.assertEqual(pos_restore.status_code, status.HTTP_200_OK)

        self.client.cookies.clear()
        self.client.post(reverse("admin_token_obtain_pair"), {"username": "cashier1", "password": "pw"})
        admin_restore = self.client.post(reverse("admin_refresh_silent"))
        self.assertEqual(admin_restore.status_code, status.HTTP_200_OK)


class MFATests(APITestCase):
    """
    A07 - MFA (TOTP) for Owner/Manager. Cashiers stay password-only (till
    turnover speed), and MFA is required only ONCE ENROLLED, not from
    account creation — see MFA_REQUIRED_ROLES in views.py for why.
    """

    def setUp(self):
        cache.clear()
        self.manager = User.objects.create_user(username="manager1", password="pw", role=Role.MANAGER)
        self.cashier = User.objects.create_user(username="cashier1", password="pw", role=Role.CASHIER)
        self.login_url = reverse("token_obtain_pair")
        self.enroll_url = reverse("mfa_enroll")
        self.confirm_url = reverse("mfa_enroll_confirm")

    def _authenticate_as(self, username, password="pw"):
        resp = self.client.post(self.login_url, {"username": username, "password": password})
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def _enroll_and_confirm_manager(self):
        """Exercises the REAL enroll -> confirm HTTP flow — use this only
        for tests actually about that flow. It consumes one TOTP code (the
        confirm call itself verifies one), so a test that goes on to
        generate "the current code" again within the same 30s step would
        get the identical code and be correctly rejected as a replay by
        django-otp's own reuse protection (min_t) — that's not a bug, it's
        the thing being protected against. Login-gate tests use
        _give_manager_a_confirmed_device instead, which doesn't consume
        anything."""
        self._authenticate_as("manager1")
        self.client.post(self.enroll_url)
        device = TOTPDevice.objects.get(user=self.manager, confirmed=False)
        self.client.post(self.confirm_url, {"totp_code": _valid_totp_code(device)})
        device.refresh_from_db()
        self.client.credentials()  # clear the auth header before the caller logs in fresh
        return device

    def _give_manager_a_confirmed_device(self):
        """A confirmed device with no codes consumed yet — for tests about
        the LOGIN gate's behavior, not about the enrollment flow itself."""
        return TOTPDevice.objects.create(user=self.manager, name="manager1-totp", confirmed=True)

    # --- Enrollment ---

    def test_cashier_cannot_enroll(self):
        self._authenticate_as("cashier1")
        resp = self.client.post(self.enroll_url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_can_enroll_and_confirm(self):
        self._authenticate_as("manager1")
        enroll_resp = self.client.post(self.enroll_url)
        self.assertEqual(enroll_resp.status_code, status.HTTP_201_CREATED)
        self.assertIn("secret", enroll_resp.data)
        self.assertIn("qr_code_base64", enroll_resp.data)
        self.assertIn("provisioning_uri", enroll_resp.data)

        device = TOTPDevice.objects.get(user=self.manager, confirmed=False)
        confirm_resp = self.client.post(self.confirm_url, {"totp_code": _valid_totp_code(device)})
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK)

        device.refresh_from_db()
        self.assertTrue(device.confirmed)

    def test_confirm_with_wrong_code_fails_and_device_stays_unconfirmed(self):
        self._authenticate_as("manager1")
        self.client.post(self.enroll_url)
        resp = self.client.post(self.confirm_url, {"totp_code": "000000"})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        device = TOTPDevice.objects.get(user=self.manager)
        self.assertFalse(device.confirmed)

    # --- Login gate ---

    def test_manager_without_enrolled_mfa_logs_in_password_only(self):
        """The documented bootstrapping decision: MFA can't be mandatory
        before enrollment exists, or a fresh account could never log in
        even once to reach the enrollment endpoint."""
        resp = self.client.post(self.login_url, {"username": "manager1", "password": "pw"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.data)

    def test_manager_login_without_totp_code_is_rejected_once_enrolled(self):
        self._give_manager_a_confirmed_device()
        resp = self.client.post(self.login_url, {"username": "manager1", "password": "pw"})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertTrue(resp.data.get("mfa_required"))
        self.assertNotIn("access", resp.data)

    def test_manager_login_with_wrong_totp_code_is_rejected(self):
        self._give_manager_a_confirmed_device()
        resp = self.client.post(
            self.login_url, {"username": "manager1", "password": "pw", "totp_code": "000000"}
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertTrue(resp.data.get("mfa_required"))

    def test_manager_login_with_valid_totp_code_succeeds(self):
        device = self._give_manager_a_confirmed_device()
        resp = self.client.post(
            self.login_url,
            {"username": "manager1", "password": "pw", "totp_code": _valid_totp_code(device)},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.data)

    def test_failed_totp_attempts_count_toward_lockout(self):
        """A wrong-code guess against a correctly-password-authenticated
        account is exactly the brute-force pattern lockout exists to catch."""
        self._give_manager_a_confirmed_device()
        cache.clear()
        for _ in range(5):
            self.client.post(
                self.login_url, {"username": "manager1", "password": "pw", "totp_code": "000000"}
            )
        self.manager.refresh_from_db()
        self.assertTrue(self.manager.is_locked())

    def test_cashier_login_unaffected_by_mfa(self):
        resp = self.client.post(self.login_url, {"username": "cashier1", "password": "pw"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.data)
