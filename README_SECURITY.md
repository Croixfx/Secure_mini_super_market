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
| Refresh token in an httpOnly, Secure (env-driven), SameSite=Lax cookie — never in a JSON body or JS-reachable storage | `views.py: _RefreshCookieMixin`, `auth/*/refresh-silent/` | A02 (XSS token theft) |
| MFA (TOTP) required for Owner/Manager once enrolled — self-service enrollment via QR code, second factor checked after password verification | `views.py: MFAEnrollView`, `MFAEnrollConfirmView`, `CustomTokenObtainPairView` | A07 |
| Wrong/missing TOTP code counts toward the same lockout as a wrong password | `views.py: CustomTokenObtainPairView.post` | A07 (brute force) |

**Known, deliberate gap:** MFA is required *once a Owner/Manager account has
enrolled a confirmed device* — not from account creation. Accounts here are
provisioner-created (no self-registration), so a brand-new Owner/Manager
account has no TOTP device yet; making MFA mandatory before enrollment
exists would mean that account could never log in even once to reach the
enrollment endpoint. Practical consequence: an Owner/Manager who never
bothers to enroll is not actually protected by a second factor. Worth a
future increment — e.g. an admin-dashboard banner nudging unenrolled
Owner/Manager accounts, or blocking access to sensitive actions (not login
itself) until MFA is set up.

## Rate limiting (checkout)

| Control | Where | OWASP category |
|---|---|---|
| Checkout endpoint rate-limited (30/min, per authenticated user) | `sales/views.py: CheckoutView` (`settings.py: DEFAULT_THROTTLE_RATES["checkout"]`) | A04 |

**Why 30/min, not the 5/min used for login:** login throttling is
deliberately tight — a handful of wrong-password attempts is already
suspicious, so slowing an attacker down matters more than accommodating
legitimate speed. Checkout is the opposite case: it's a till in active,
legitimate use, and a fast cashier scanning a short cart and hitting pay
can genuinely complete a sale every few seconds during a rush. 30/min is
one sale every 2 seconds sustained — well above realistic human checkout
speed — so it bounds a compromised token or a buggy/looping client without
being reachable by normal till use. `ScopedRateThrottle` keys the count by
authenticated user (not IP), so one busy till maxing out its own budget
has no effect on any other cashier's till — verified directly (see below).

**Verified, not assumed:**
- Automated: `sales/tests.py: CheckoutThrottleTests` proves the 31st
  checkout within a minute for one user gets `429`, and that a second
  user's till is completely unaffected by the first hitting its limit.
- Manual, against the real running dev server (not the test DB): 5 real
  checkouts via the POS terminal UI at human/fast-tap speed all succeeded
  (`201`, confirmed in the server log), never throttled. A scripted burst
  of 35 checkouts fired back-to-back (0.52s total, far faster than any
  real till) succeeded exactly 30 times, then correctly returned `429`
  with `Retry-After: 60` from request 31 onward. Triggering that same
  burst from the actual POS UI showed the cashier a clear inline message
  ("Request was throttled. Expected available in N seconds.") rather than
  a crash — the cart and idempotency key are preserved, so retrying after
  the cooldown completes the original sale, not a duplicate. Once the
  60-second window rolled forward, the next attempt succeeded normally
  with no manual intervention needed.

## HTTPS / Transport Security

| Control | Where | OWASP category |
|---|---|---|
| HTTPS redirect, secure session/CSRF cookies, HSTS — all default ON once `DEBUG=False`, default OFF only for local dev | `settings.py: SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`, `SECURE_HSTS_INCLUDE_SUBDOMAINS` | A05 |

**The gap found and fixed:** these five settings were already read from the
environment (`env.bool(...)`, `env.int(...)`), so they were never literally
hardcoded — but four of the five fell back to **off regardless of `DEBUG`**
when their env var wasn't set, unlike `ALLOWED_HOSTS` just above them in the
same file, which already does `default=["*"] if DEBUG else []`. Practical
consequence: deploy with `DEBUG=False` and forget to *also* set these four
env vars, and the app would silently run in production with no HTTPS
redirect, non-secure cookies, and no HSTS — exactly the kind of gap that
doesn't show up until it matters.

**Fix:** each now defaults to `not DEBUG` — secure unless you're in local
dev, same branching pattern `ALLOWED_HOSTS` already used. Still individually
overridable via env for a deployment that deliberately needs something
different (e.g. TLS terminated elsewhere).

**Verified, not assumed** — resolved values with no env vars set at all,
before vs. after:

| Setting | Local dev (`DEBUG` unset → `True`) | Prod-shaped (`DEBUG=False`), before fix | Prod-shaped (`DEBUG=False`), after fix |
|---|---|---|---|
| `SECURE_SSL_REDIRECT` | `False` | `False` | `True` |
| `SESSION_COOKIE_SECURE` | `False` | `False` | `True` |
| `CSRF_COOKIE_SECURE` | `False` | `False` | `True` |
| `SECURE_HSTS_SECONDS` | `0` | `0` | `31536000` (1 year) |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `False` | `False` | `True` |

Also cross-checked against Django's own `manage.py check --deploy`
checklist: with `DEBUG=False` and no other env vars set, this dropped from
6 warnings (including `security.W004` HSTS, `W008` SSL redirect, `W012`
session cookie, `W016` CSRF cookie — the exact four this fix addresses) to
3 (the two that are legitimately still the deployer's job — a real
`SECRET_KEY` and a real `ALLOWED_HOSTS` — plus an optional `W021` HSTS
preload suggestion, not requested here).

**The one setting that needed a visible exception, not a silent one:**
`SECURE_SSL_REDIRECT` 301-redirects any request Django sees as non-HTTPS.
CI intentionally runs with `DEBUG=False` (to exercise the same settings
branch production uses), but Django's test client talks to the app over
plain HTTP — forcing the redirect on turned every expected `200`/`401`
into a `301` (confirmed by actually running the suite that way before
deciding on the fix, not assumed). Rather than carve out an exception
inside `settings.py` that would silently apply everywhere `DEBUG=False` is
used, `.github/workflows/ci.yml` now sets `SECURE_SSL_REDIRECT: "False"`
explicitly, with a comment explaining why — the override is visible in the
one place it's needed, not baked into the default.

**Known deployment-topology caveat:** if this app ever sits behind a
reverse proxy that terminates TLS (nginx, a load balancer, etc.), Django's
`request.is_secure()` won't see the original connection as HTTPS unless
`SECURE_PROXY_SSL_HEADER` is also configured to trust `X-Forwarded-Proto`
from that specific proxy — without it, `SECURE_SSL_REDIRECT=True` would
cause a redirect loop. Deliberately not configured here: trusting that
header blindly without knowing the real proxy topology is its own spoofing
risk, the same class of issue as the `X-Forwarded-For` caveat below.
Setting it correctly is the deployer's responsibility, same as
`ALLOWED_HOSTS`.

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
root. That config excludes `*/tests.py`, `*/tests_*.py`, `*/migrations/*`,
and `*/venv/*` from the scan.

Test files are excluded deliberately, not silently: `accounts/tests.py`,
`inventory/tests.py`, and `inventory/tests_movements.py` create users with
literal strings like `password="pw"` as fixture data for `APITestCase` —
these trip bandit's `B106`/`B107` ("hardcoded_password_funcarg" /
"hardcoded_password_default") rules. That's a false positive, not a
finding — the strings aren't credentials for any real account, they never
leave the test database, and flagging them adds noise to every scan
without surfacing an actual secret. The exclude pattern is `*/tests_*.py`
rather than one entry per file, so it also covers whatever the next
`tests_<feature>.py` file turns out to be named. Migrations are excluded
because they're generated code, not hand-written logic. `venv/` is
excluded because bandit should scan the project's own code, not its
third-party dependencies (`pip-audit`, also in `requirements.txt`, is the
right tool for dependency vulnerabilities).

One finding is suppressed inline rather than by path:
`inventory/management/commands/seed_demo_data.py` hardcodes a demo
password (`# nosec B105`). Unlike test fixtures, this file isn't excluded
wholesale — it's real seeding logic that deserves normal scanning, and only
the one line is a known non-secret (a published demo credential, and the
command refuses to run outside `DEBUG`, so it can never seed a real
deployment).

Real hardcoded-password findings in application code (`models.py`,
`views.py`, `serializers.py`, etc.) are still in scope and would still be
reported — only the three excluded path patterns above are skipped.

## Cross-Site Request Forgery (CSRF)

**Why the JWT-in-header API calls (POS/admin product, sales, stock, and
user-management endpoints) are not CSRF-vulnerable:** CSRF works by having
a victim's browser send an authenticated request the victim didn't intend —
which requires the browser to attach the victim's credentials
*automatically*. A cross-site page can trigger a request to this API, but
it cannot make the victim's browser attach an `Authorization: Bearer
<token>` header, because that header is set by our own frontend JS reading
an in-memory value, not something the browser attaches on its own the way
it does cookies. A forged request from another site arrives with no
credential at all and gets `401`.

**Why the new httpOnly refresh cookie (added for the session-restore flow)
doesn't reintroduce that gap:** the cookie *is* something the browser
attaches automatically, so the reasoning has to be made explicitly rather
than inherited for free:

1. The cookie is `SameSite=Lax`. Browsers exclude `Lax` cookies from
   cross-site POST/fetch/XHR requests — exactly the request shape a CSRF
   attack against a JSON API needs. They're only sent on cross-site
   top-level `GET` navigations (e.g. following a link).
2. Because of (1), the CSRF argument for a `Lax` cookie only fully holds if
   **no state-changing action in this API is reachable via GET** — a GET
   is the one cross-site request shape the cookie still rides along with.
   This was verified directly, not assumed:
   - Every custom endpoint that changes state — `auth/login/`,
     `auth/pos/login/`, `auth/admin/login/`, `auth/refresh-silent/` (and
     its `pos`/`admin` variants), `auth/logout/` (and its `pos`/`admin`
     variants), `auth/refresh/`, `sales/checkout/`,
     `inventory/stock/record_wastage/`, and
     `inventory/stock/stocktake_adjustment/` — was hit with `GET` and
     confirmed to return `405 Method Not Allowed`, never processed.
   - Every `ModelViewSet` (`users`, `categories`, `products`, `stock`)
     routes GET to `list`/`retrieve` only — DRF's router maps HTTP verbs to
     actions structurally (GET → read, POST/PUT/PATCH/DELETE → write),
     so there's no code path where a GET request reaches `create`,
     `update`, or `destroy`. Confirmed empirically too: object counts for
     products and users were captured before and after issuing GETs to
     their collection endpoints, and were unchanged.
3. Even in a hypothetical where (1) failed (e.g. a very old browser with no
   `SameSite` support), `CORS_ALLOWED_ORIGINS`'s strict allowlist means a
   forged cross-origin request can't read the response — only the
   browser-level "was a cookie attached" question is in play, not "can the
   attacker see the result."

Net: the refresh cookie is exempted from Django's CSRF token middleware
deliberately, not by omission — `SameSite=Lax` plus "no mutation is ever
GET-reachable" plus the CORS allowlist together cover the same ground a
CSRF token would, without forcing a stateless JWT flow to carry one.

## Known gaps (tracked honestly, not hidden)

- MFA enrollment is opt-in per account (see the Authentication table above)
  — an Owner/Manager who never enrolls stays password-only.
- No MFA "disable" endpoint yet — an enrolled account's only way to remove
  a device today is direct DB access. Small, deliberately deferred.
- IP-based rate limiting here is application-level only; a reverse proxy /
  WAF layer (e.g. nginx `limit_req`, or Cloudflare) should back this up in
  production — defense in depth, not a single control.
- `HTTP_X_FORWARDED_FOR` is trusted for audit logging in `views.py`; this is
  only safe if the deployment sits behind a proxy you control that strips
  client-supplied values for this header before setting its own.
