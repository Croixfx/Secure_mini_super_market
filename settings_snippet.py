"""
settings_snippet.py

Not an importable module — copy the relevant blocks into your project's
settings.py. Kept separate and heavily commented so it doubles as
documentation of *why* each setting exists, which is what you'll want to
point to in an interview.
"""

# ── Identity ─────────────────────────────────────────────────────────────
AUTH_USER_MODEL = "accounts.CustomUser"

INSTALLED_APPS = [
    # ...
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",  # required for refresh-token revocation on logout
    "accounts",
    # "django_otp", "django_otp.plugins.otp_totp",  # add when you build MFA for Owner/Manager
]

# ── A02: Cryptographic Failures — password hashing ──────────────────────
# Argon2 first in the list = Argon2 used for all NEW password hashes.
# Django auto-upgrades existing PBKDF2 hashes to Argon2 on next successful
# login, so no forced password reset is needed when you adopt this.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ── A07: Identification & Authentication Failures — JWT config ─────────
from datetime import timedelta  # noqa: E402

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,  # old refresh token becomes unusable the instant it's rotated
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    # In production, prefer RS256 with a private/public keypair so the
    # signing key never has to live on any service that only verifies tokens.
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    # Deny by default; every view opts INTO access rather than opting out of it.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    # A04: Insecure Design — blunt brute force / credential stuffing at the
    # framework level, in addition to any WAF/reverse-proxy rate limiting.
    "DEFAULT_THROTTLE_RATES": {
        "login": "5/min",
        "checkout": "30/min",
    },
}

# ── A05: Security Misconfiguration ──────────────────────────────────────
DEBUG = False  # never True in production; use a separate settings_dev.py locally
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True

# CORS: allow only the known frontend origins, never "*"
# CORS_ALLOWED_ORIGINS = ["https://pos.yourdomain.rw", "https://admin.yourdomain.rw"]

# ── Secrets ──────────────────────────────────────────────────────────────
# SECRET_KEY, DB credentials, MoMo API keys: load from environment variables
# (e.g. via django-environ), never hardcoded, never committed. Pair with a
# gitleaks pre-commit hook so an accidental commit is caught before push.
