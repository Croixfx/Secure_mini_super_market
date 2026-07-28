"""
accounts/serializers.py

OWASP mapping:
- A01 / A08 (mass assignment): UserSerializer explicitly whitelists writable
  fields so a client can never PATCH e.g. `is_superuser` or `failed_login_attempts`
  even if they guess the field name.
- A02 (Cryptographic Failures): password is write_only and passed through
  Django's set_password (Argon2 hasher configured in settings), never stored
  or returned in plaintext.
"""
from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Adds role/branch into the JWT payload so the frontend can render the
    right UI without an extra round trip — but authorization decisions on
    the backend NEVER trust these claims alone; every view re-checks
    request.user.role/branch against the database on each request."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        token["branch_id"] = user.branch_id
        # Lets the frontend redisplay "logged in as <username>" after a
        # silent session restore (refresh-silent), where there's no login
        # form input to read it from. Not sensitive — it's the user's own
        # username, already known to them.
        token["username"] = user.username
        return token


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=10)

    class Meta:
        model = User
        # Explicit allow-list. Anything not listed here (is_superuser,
        # is_staff, failed_login_attempts, locked_until, ...) can never be
        # set via this API, no matter what the client sends.
        fields = ["id", "username", "email", "role", "branch", "password", "is_active"]
        read_only_fields = ["id"]

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance
