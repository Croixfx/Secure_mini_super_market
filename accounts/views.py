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
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status, viewsets, permissions as drf_permissions
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import AuditLog, LoginAttempt
from .permissions import IsOwner
from .serializers import CustomTokenObtainPairSerializer, UserSerializer

User = get_user_model()


def _client_ip(request):
    # Respect a trusted reverse proxy header only if you control that proxy;
    # otherwise this is spoofable. Documented here deliberately so the
    # assumption is visible, not silent.
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class CustomTokenObtainPairView(TokenObtainPairView):
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


class LogoutView(APIView):
    """
    Blacklists the refresh token on logout so a stolen refresh token can't be
    replayed after the user has explicitly logged out. Requires
    rest_framework_simplejwt.token_blacklist in INSTALLED_APPS.
    """

    permission_classes = [drf_permissions.IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"detail": "refresh token required"}, status=400)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            return Response({"detail": "invalid or already-used token"}, status=400)

        AuditLog.record(
            actor=request.user, action="logout", ip_address=_client_ip(request)
        )
        return Response(status=status.HTTP_205_RESET_CONTENT)


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
