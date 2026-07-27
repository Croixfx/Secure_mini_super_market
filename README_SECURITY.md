# Feature 1: Identity & Access — Security Design

This document maps the `accounts` app to OWASP's AAA model (Authentication,
Authorization, Accounting) and the relevant OWASP Top 10 (2021) categories.
It's meant to sit in the repo root (or be linked from the main README) as
the artifact a reviewer reads *before* the code.

## Authentication

| Control | Where | OWASP category |
|---|---|---|
| Argon2 password hashing, auto-upgrade from PBKDF2 | `settings_snippet.py` | A02 |
| No public self-registration; accounts provisioned by Owner only | `urls.py` (no register endpoint) | A07 |
| Account lockout after 5 failed attempts, 15 min cooldown | `models.py: register_failed_login` | A07 |
| Lockout checked *before* password verification | `views.py: CustomTokenObtainPairView` | A07 |
| Generic error response — locked / wrong password / unknown user all look identical | `views.py` | A07 (username enumeration) |
| Short-lived (15 min) access tokens, rotating refresh tokens with reuse-blacklisting | `settings_snippet.py: SIMPLE_JWT` | A07 |
| Refresh token blacklisted explicitly on logout | `views.py: LogoutView` | A07 |
| Login endpoint rate-limited (5/min) independent of any WAF | `settings_snippet.py: DEFAULT_THROTTLE_RATES` | A04 |
| Minimum 10-char passwords, common-password + similarity checks | `settings_snippet.py: AUTH_PASSWORD_VALIDATORS` | A07 |

**Not yet built, flagged deliberately:** MFA (TOTP) for Owner/Manager roles —
`django-otp` is commented into `INSTALLED_APPS` as the next increment.

## Authorization

| Control | Where | OWASP category |
|---|---|---|
| Role stored on the user record, never trusted from a client-supplied header/claim for backend decisions | `models.py: Role` | A01 |
| `IsOwner` / `IsBranchManagerOrOwner` — view-level role gates | `permissions.py` | A01 |
| `IsSameBranchOrOwner` — object-level branch scoping (defeats IDOR) | `permissions.py` | A01 |
| Every ViewSet's `get_queryset()` filters by branch, not just the permission class | `views.py: UserAdminViewSet.get_queryset` | A01 |
| Serializer explicit field allow-list — no mass assignment of `is_superuser`, lockout fields, etc. | `serializers.py: UserSerializer.Meta.fields` | A08 |
| Default DRF permission is `IsAuthenticated` — deny by default, opt in per view | `settings_snippet.py` | A01 |

**Design principle carried through the whole system, not just this app:**
permission classes stop the wrong *role*; queryset scoping stops the right
role from reaching the wrong *branch*. Every other app (sales, inventory,
transfers) must repeat both halves — a permission check alone is not
sufficient in a multi-branch system.

## Accounting (audit & monitoring)

| Control | Where | OWASP category |
|---|---|---|
| Every login attempt (success/failure) recorded with IP, user agent | `models.py: LoginAttempt` | A09 |
| Structured, queryable audit log for sensitive actions (login, logout, role changes, user creation) | `models.py: AuditLog` | A09 |
| Before/after values captured on role changes | `views.py: UserAdminViewSet.perform_update` | A09 |
| Indexed by (ip, time) and (username, time) to support brute-force detection queries | `models.py: LoginAttempt.Meta.indexes` | A09 |

**Next increment:** an alerting rule (Celery periodic task) that flags "N
failed logins from one IP within 5 minutes" — the query is trivial against
the indexes already in place; only the notification wiring is missing.

## How to verify these claims yourself

Run the test suite in `tests.py` — it's written to prove the properties
above, not just exercise the happy path:

```
python manage.py test accounts
```

Specifically:
- `AuthenticationLockoutTests` — proves lockout triggers, and that locked
  accounts are rejected even with the correct password.
- `BranchScopedAccessControlTests` — proves a lower-privileged role is
  blocked from an admin endpoint (the IDOR-style test pattern to repeat for
  every other app's viewsets).
- `MassAssignmentProtectionTests` — proves a client cannot escalate
  privilege by adding unexpected fields to a create request.

## Static analysis scope

`bandit` (in `requirements.txt` as a dev/CI dependency) runs against this
repo via `bandit -r .`, configured by the `.bandit` file at the project
root. That config excludes `*/tests.py`, `*/migrations/*`, and `*/venv/*`
from the scan.

Test files are excluded deliberately, not silently: `accounts/tests.py`
creates users with literal strings like `password="pw"` as fixture data for
`APITestCase` — these trip bandit's `B106`/`B107`
("hardcoded_password_funcarg" / "hardcoded_password_default") rules. That's
a false positive, not a finding — the strings aren't credentials for any
real account, they never leave the test database, and flagging them adds
noise to every scan without surfacing an actual secret. Migrations are
excluded because they're generated code, not hand-written logic. `venv/` is
excluded because bandit should scan the project's own code, not its
third-party dependencies (`pip-audit`, also in `requirements.txt`, is the
right tool for dependency vulnerabilities).

Real hardcoded-password findings in application code (`models.py`,
`views.py`, `serializers.py`, etc.) are still in scope and would still be
reported — only the three excluded path patterns above are skipped.

## Known gaps (tracked honestly, not hidden)

- MFA not yet implemented for privileged roles.
- IP-based rate limiting here is application-level only; a reverse proxy /
  WAF layer (e.g. nginx `limit_req`, or Cloudflare) should back this up in
  production — defense in depth, not a single control.
- `HTTP_X_FORWARDED_FOR` is trusted for audit logging in `views.py`; this is
  only safe if the deployment sits behind a proxy you control that strips
  client-supplied values for this header before setting its own.
