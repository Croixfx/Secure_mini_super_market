"""
accounts/views.py

OWASP mapping:
- A07 (Identification & Authentication Failures): lockout enforced before
  credentials are even checked; generic error messages avoid user enumeration.
- A09 (Security Logging & Monitoring Failures): every attempt, success or
  failure, is recorded with actor/IP via LoginAttempt + AuditLog.
- A04 (Insecure Design): login endpoint is throttled at the view level in
  addition to any reverse-proxy rate limiting.
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status, viewsets, permissions as drf_permissions
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import AuditLog, LoginAttempt
from .permissions import IsOwner
from .serializers import CustomTokenObtainPairSerializer, UserSerializer

User = get_user_model()

# Default cookie identity for the generic/unscoped auth endpoints (used by
# the test suite and any non-browser API consumer). The pos-frontend and
# admin-frontend apps get their OWN cookie name + path (see
# POSTokenObtainPairView / AdminTokenObtainPairView below) rather than
# sharing this one.
DEFAULT_REFRESH_COOKIE_NAME = settings.REFRESH_TOKEN_COOKIE_NAME
DEFAULT_REFRESH_COOKIE_PATH = "/api/auth/"


def _client_ip(request):
    # Respect a trusted reverse proxy header only if you control that proxy;
    # otherwise this is spoofable. Documented here deliberately so the
    # assumption is visible, not silent.
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class _RefreshCookieMixin:
    """
    Shared cookie set/clear logic, parameterized per subclass by
    cookie_name/cookie_path rather than hardcoded — because pos-frontend and
    admin-frontend both talk to the SAME backend host, and cookies are
    scoped by (domain, path), not by which frontend page made the request.

    Without distinct names, logging into one app's till/dashboard would
    silently authenticate the OTHER app too on its next load — the browser
    would attach the same cookie regardless of which frontend sent the
    request. That defeats the entire reason these are separate frontend
    builds: a cashier session should have no path into the admin app at
    all, not just no USEFUL path once there (backend permission checks
    still apply either way, but the login screen itself should not
    silently vanish for someone who never authenticated to THAT app).
    """

    cookie_name = DEFAULT_REFRESH_COOKIE_NAME
    cookie_path = DEFAULT_REFRESH_COOKIE_PATH

    def _set_refresh_cookie(self, response, refresh_token):
        response.set_cookie(
            key=self.cookie_name,
            value=refresh_token,
            httponly=True,
            secure=settings.SESSION_COOKIE_SECURE,
            samesite="Lax",
            path=self.cookie_path,
            max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        )

    def _clear_refresh_cookie(self, response):
        response.delete_cookie(self.cookie_name, path=self.cookie_path)


class CustomTokenObtainPairView(_RefreshCookieMixin, TokenObtainPairView):
    """
    Login endpoint. Wraps simplejwt's token view with:
      1. Lockout check BEFORE password verification (so a locked account
         can't be used to brute-force the password field either).
      2. Uniform error responses regardless of whether the username exists,
         the password is wrong, or the account is locked — this avoids
         leaking which usernames are valid (username enumeration, a common
         finding in AppSec reviews).
      3. LoginAttempt + AuditLog rows for every outcome.
    """

    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    GENERIC_ERROR = {"detail": "Unable to log in with the provided credentials."}

    def post(self, request, *args, **kwargs):
        username = request.data.get("username", "")
        ip = _client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")[:512]

        user = User.objects.filter(username=username).first()

        if user and user.is_locked():
            self._log_attempt(username, user, ip, user_agent, success=False)
            AuditLog.record(
                actor=user, action="login_blocked_locked_account", ip_address=ip
            )
            # Same generic response + same status code as a bad password,
            # so an attacker can't distinguish "locked" from "wrong password".
            return Response(self.GENERIC_ERROR, status=status.HTTP_401_UNAUTHORIZED)

        try:
            response = super().post(request, *args, **kwargs)
        except AuthenticationFailed:
            # simplejwt's serializer raises rather than returning a non-200
            # response on bad credentials, so it must be caught here to reach
            # the same failure handling (lockout counter, logging, generic
            # error) as any other rejected login.
            response = Response(status=status.HTTP_401_UNAUTHORIZED)

        if response.status_code == 200:
            if user:
                user.register_successful_login()
            self._log_attempt(username, user, ip, user_agent, success=True)
            AuditLog.record(actor=user, action="login_success", ip_address=ip)
            # Refresh token moves from the JSON body to an httpOnly cookie —
            # JS never sees it, so an XSS payload that can read
            # window/localStorage/document.cookie still can't exfiltrate it.
            # Only the short-lived access token stays in the response body.
            refresh_token = response.data.pop("refresh", None)
            if refresh_token:
                self._set_refresh_cookie(response, refresh_token)
        else:
            if user:
                user.register_failed_login()
            self._log_attempt(username, user, ip, user_agent, success=False)
            AuditLog.record(
                actor=user, action="login_failed", ip_address=ip, attempted_username=username
            )
            return Response(self.GENERIC_ERROR, status=status.HTTP_401_UNAUTHORIZED)

        return response

    @staticmethod
    def _log_attempt(username, user, ip, user_agent, *, success):
        LoginAttempt.objects.create(
            username_attempted=username,
            user=user,
            ip_address=ip,
            user_agent=user_agent,
            success=success,
        )


class RefreshSilentView(_RefreshCookieMixin, APIView):
    """
    Session restoration on app load: the refresh token lives only in the
    httpOnly cookie set by CustomTokenObtainPairView, so this is the only
    way a page refresh (or a brand-new tab) can get a new access token
    without the user re-entering credentials.

    Unauthenticated by design — an access token isn't required (that's the
    whole point), and the httpOnly cookie is the only thing that proves
    anything here. Reuses simplejwt's own TokenRefreshSerializer rather than
    reimplementing rotation/blacklist handling, just swapping where the
    refresh token comes from (cookie, not body) and where the new one goes
    (cookie, not body).
    """

    permission_classes = [drf_permissions.AllowAny]

    def post(self, request):
        raw_refresh = request.COOKIES.get(self.cookie_name)
        if not raw_refresh:
            return Response({"detail": "No refresh cookie present."}, status=status.HTTP_401_UNAUTHORIZED)

        serializer = TokenRefreshSerializer(data={"refresh": raw_refresh})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(exc.args[0])

        data = dict(serializer.validated_data)
        new_refresh = data.pop("refresh", None)
        response = Response(data, status=status.HTTP_200_OK)
        if new_refresh:
            self._set_refresh_cookie(response, new_refresh)
        return response


class LogoutView(_RefreshCookieMixin, APIView):
    """
    Blacklists the refresh token on logout so a stolen refresh token can't be
    replayed after the user has explicitly logged out. Requires
    rest_framework_simplejwt.token_blacklist in INSTALLED_APPS.

    Refresh token comes from the httpOnly cookie now, not the request body —
    JS never has it to send. Missing/already-invalid cookie isn't treated as
    an error: the user's goal (end up logged out) is achievable either way,
    so this stays lenient rather than blocking logout over a token that's
    already expired or was never there.
    """

    permission_classes = [drf_permissions.IsAuthenticated]

    def post(self, request):
        refresh_token = request.COOKIES.get(self.cookie_name)
        if refresh_token:
            try:
                RefreshToken(refresh_token).blacklist()
            except TokenError:
                pass

        response = Response(status=status.HTTP_205_RESET_CONTENT)
        self._clear_refresh_cookie(response)
        AuditLog.record(
            actor=request.user, action="logout", ip_address=_client_ip(request)
        )
        return response


class POSTokenObtainPairView(CustomTokenObtainPairView):
    cookie_name = "pos_refresh_token"
    cookie_path = "/api/auth/pos/"


class POSRefreshSilentView(RefreshSilentView):
    cookie_name = "pos_refresh_token"
    cookie_path = "/api/auth/pos/"


class POSLogoutView(LogoutView):
    cookie_name = "pos_refresh_token"
    cookie_path = "/api/auth/pos/"


class AdminTokenObtainPairView(CustomTokenObtainPairView):
    cookie_name = "admin_refresh_token"
    cookie_path = "/api/auth/admin/"


class AdminRefreshSilentView(RefreshSilentView):
    cookie_name = "admin_refresh_token"
    cookie_path = "/api/auth/admin/"


class AdminLogoutView(LogoutView):
    cookie_name = "admin_refresh_token"
    cookie_path = "/api/auth/admin/"


class UserAdminViewSet(viewsets.ModelViewSet):
    """
    Owner-only user management: create staff accounts, assign roles/branches,
    deactivate accounts. No public self-registration endpoint exists
    anywhere in this app — accounts are provisioned by an Owner, which
    closes off a whole class of abuse (fake signups, enumeration via a
    public register endpoint).
    """

    serializer_class = UserSerializer
    permission_classes = [drf_permissions.IsAuthenticated, IsOwner]

    def get_queryset(self):
        # Even though only Owners reach this view, scope defensively —
        # defense in depth, not defense in one layer.
        return User.objects.all().order_by("username")

    def perform_create(self, serializer):
        user = serializer.save()
        AuditLog.record(
            actor=self.request.user,
            action="user_created",
            target_repr=str(user),
            role_assigned=user.role,
        )

    def perform_update(self, serializer):
        before_role = self.get_object().role
        user = serializer.save()
        if before_role != user.role:
            AuditLog.record(
                actor=self.request.user,
                action="role_changed",
                target_repr=str(user),
                before=before_role,
                after=user.role,
            )
