"""
Django settings for the mini_super_market project.

Built from settings_snippet.py (see README_SECURITY.md for the rationale
behind each security-related setting). Values that must differ between dev
and production (DEBUG, SECRET_KEY, HTTPS-only cookies/redirects) are read
from the environment so this one settings module works in both.
"""
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, True),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="dev-only-insecure-secret-key-change-me")
DEBUG = env.bool("DEBUG", default=True)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["*"] if DEBUG else [])

# ── Identity ─────────────────────────────────────────────────────────────
AUTH_USER_MODEL = "accounts.CustomUser"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "branches",
    "accounts",
    "inventory",
    "sales",
    "procurement",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ── A02: Cryptographic Failures — password hashing ──────────────────────
# Argon2 first in the list = Argon2 used for all NEW password hashes.
# Django auto-upgrades existing PBKDF2 hashes to Argon2 on next successful
# login, so no forced password reset is needed when you adopt this.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Kigali"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── A07: Identification & Authentication Failures — MFA (TOTP) ─────────
# Cosmetic only (shows up as the account label in the user's authenticator
# app) — has no effect on token verification.
OTP_TOTP_ISSUER = "Mini Supermarket"

# ── A07: Identification & Authentication Failures — JWT config ─────────
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
}

# The refresh token is never returned in a JSON body or stored in JS-reachable
# storage — it lives ONLY in this httpOnly cookie, so an XSS payload that can
# read window/localStorage/document.cookie still can't exfiltrate it. Reuses
# SESSION_COOKIE_SECURE's env-driven flag rather than a separate setting,
# since "are we behind HTTPS" is one fact, not two.
REFRESH_TOKEN_COOKIE_NAME = "refresh_token"  # nosec B105 - a cookie NAME, not a credential value

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "login": "5/min",
        "checkout": "30/min",
    },
}

# ── A05: Security Misconfiguration ──────────────────────────────────────
# Defaults branch on DEBUG the same way ALLOWED_HOSTS does above: secure
# unless you're in local dev (DEBUG=True, no TLS available). This means a
# `DEBUG=False` deploy is safe by default even if nobody sets these env
# vars explicitly — they're still individually overridable via env for a
# staging setup that deliberately terminates TLS elsewhere, but the
# fallback is no longer "silently off in production."
#
# SECURE_SSL_REDIRECT is the one exception requiring a visible override:
# it 301-redirects any request Django sees as non-HTTPS, and CI runs with
# DEBUG=False (to exercise prod-shaped settings) while talking to the app
# over plain HTTP via Django's test client — confirmed by running the
# suite with it forced on, which turned every 200/401 into a 301. CI's
# workflow file sets SECURE_SSL_REDIRECT=False explicitly, with a comment,
# rather than this file silently exempting it.
#
# If this is ever deployed behind a reverse proxy that terminates TLS
# (nginx, a load balancer, etc.), Django's request.is_secure() won't see
# the original connection as HTTPS unless SECURE_PROXY_SSL_HEADER is also
# configured to trust X-Forwarded-Proto from that specific proxy — without
# it, turning this on would cause a redirect loop. Deliberately not
# configured here (blindly trusting X-Forwarded-Proto without knowing the
# real proxy topology is its own spoofing risk — same class of issue as
# the X-Forwarded-For caveat below); it's the deployer's responsibility to
# set it correctly for their actual topology, same as ALLOWED_HOSTS.
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0 if DEBUG else 31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=not DEBUG)
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=not DEBUG)
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=not DEBUG)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=not DEBUG)
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True

CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=[
        "http://localhost:5173", "http://127.0.0.1:5173",  # admin-frontend
        "http://localhost:5174", "http://127.0.0.1:5174",  # pos-frontend
    ],
)
# client.js sends credentials: "include" on every request (so a future
# httpOnly refresh-token cookie will be sent automatically once that flow is
# wired up) — without this, the browser rejects ANY credentialed cross-origin
# response outright, regardless of CORS_ALLOWED_ORIGINS being correct.
CORS_ALLOW_CREDENTIALS = True
