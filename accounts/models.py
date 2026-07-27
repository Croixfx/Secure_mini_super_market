"""
accounts/models.py

Identity, RBAC, and audit models for the supermarket system.

OWASP mapping:
- Authentication (AAA): CustomUser + LoginAttempt support lockout/backoff (A07).
- Authorization (AAA): role + branch fields are the source of truth for every
  permission check elsewhere in the system (A01 - Broken Access Control).
- Accounting (AAA): AuditLog gives a queryable trail for every sensitive
  action (A09 - Security Logging and Monitoring Failures).
"""
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class Role(models.TextChoices):
    OWNER = "OWNER", "Owner"
    MANAGER = "MANAGER", "Branch Manager"
    CASHIER = "CASHIER", "Cashier"


class CustomUser(AbstractUser):
    """
    Extends Django's built-in user with the two fields every authorization
    decision in this system hinges on: role and branch.

    Design decision: role and branch live on the user model itself (not a
    separate profile table) so every queryset filter and permission check can
    reference `request.user.role` / `request.user.branch` directly, with no
    join required and no room for the two tables to drift out of sync.
    """

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CASHIER)

    # Nullable because an Owner is not tied to a single branch — they see all.
    branch = models.ForeignKey(
        "branches.Branch",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="staff",
    )

    # --- Account lockout state (Authentication / A07) ---
    failed_login_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    def is_locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > timezone.now())

    def register_failed_login(self, max_attempts: int = 5, lockout_minutes: int = 15):
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= max_attempts:
            self.locked_until = timezone.now() + timezone.timedelta(minutes=lockout_minutes)
        self.save(update_fields=["failed_login_attempts", "locked_until"])

    def register_successful_login(self):
        if self.failed_login_attempts or self.locked_until:
            self.failed_login_attempts = 0
            self.locked_until = None
            self.save(update_fields=["failed_login_attempts", "locked_until"])

    def __str__(self):
        return f"{self.username} ({self.role})"


class LoginAttempt(models.Model):
    """
    One row per login attempt, success or failure. This is what powers
    brute-force detection and gives you something concrete to show an
    interviewer: 'here is how I'd detect credential stuffing.'
    """

    username_attempted = models.CharField(max_length=150)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    ip_address = models.GenericIPAddressField()
    user_agent = models.CharField(max_length=512, blank=True)
    success = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["ip_address", "created_at"]),
            models.Index(fields=["username_attempted", "created_at"]),
        ]

    def __str__(self):
        outcome = "success" if self.success else "failure"
        return f"{self.username_attempted} [{outcome}] @ {self.created_at:%Y-%m-%d %H:%M}"


class AuditLog(models.Model):
    """
    Structured audit trail for sensitive actions across the whole system —
    not just auth. Other apps (sales, inventory, transfers) should write here
    too via `AuditLog.record(...)`.

    Kept deliberately generic (action + metadata JSON) so every module can
    log through the same table without a schema migration each time.
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    action = models.CharField(max_length=100)  # e.g. "login_failed", "role_changed"
    target_repr = models.CharField(max_length=255, blank=True)  # human-readable target
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)  # before/after values, etc.
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["actor", "created_at"]),
        ]

    @classmethod
    def record(cls, *, actor, action: str, target_repr: str = "", ip_address=None, **metadata):
        return cls.objects.create(
            actor=actor,
            action=action,
            target_repr=target_repr,
            ip_address=ip_address,
            metadata=metadata,
        )

    def __str__(self):
        who = self.actor.username if self.actor else "anonymous"
        return f"{who} -> {self.action} ({self.created_at:%Y-%m-%d %H:%M})"
