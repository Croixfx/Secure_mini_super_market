# Secure_mini_super_market

![CI](https://github.com/Croixfx/Secure_mini_super_market/actions/workflows/ci.yml/badge.svg)

A multi-branch supermarket management system (Django REST API + React
admin frontend) built with a deliberate AppSec focus — every feature is
paired with the access-control tests that prove it, not just the tests
that prove it works.

## Security work done so far

- **RBAC + branch-scoped access control**, enforced at both the permission
  and queryset layer, with tests that specifically try to break it as an
  IDOR attack (a lower-privileged, correctly-authenticated user reaching
  another branch's data)
- **Argon2 password hashing**, rotating JWT refresh tokens with
  reuse-blacklisting, and account lockout after repeated failed logins
- An **append-only stock movement ledger** — every stock change is an
  immutable, attributed, timestamped row, so `Stock.quantity` can never
  silently drift from its own history
- A **CI pipeline** (GitHub Actions) that runs the full test suite, bandit
  (static security analysis), and pip-audit (dependency vulnerability
  scanning) on every push and pull request to `main`

See [`README_SECURITY.md`](./README_SECURITY.md) for the detailed
OWASP Top 10 / AAA (Authentication, Authorization, Accounting) mapping,
including which control lives where and how to verify each claim yourself.
