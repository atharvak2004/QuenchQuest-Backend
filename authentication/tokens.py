"""JWT helpers shared by volunteer and admin/employee logins.

Access token: sent as `Authorization: Bearer <token>` (24 h by default).
Refresh token: exchanged at POST /api/auth/token/refresh/ for a new pair (30 days).
Both carry `pv` (a fingerprint of the password hash), so changing a password
logs out every existing session.
"""
import hashlib
from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed

from .models import SisUser, User


def password_version(user):
    return hashlib.sha256((user.password or "").encode()).hexdigest()[:12]


def _identity(user):
    if isinstance(user, SisUser):
        return {"sisuser_id": user.id, "username": user.username, "role": user.choice}
    return {"user_id": user.id, "email": user.email}


def _encode(user, token_type, lifetime):
    now = datetime.now(timezone.utc)
    payload = {
        **_identity(user),
        "type": token_type,
        "pv": password_version(user),
        "iat": now,
        "exp": now + lifetime,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def access_token(user):
    return _encode(user, "access", timedelta(hours=settings.JWT_ACCESS_HOURS))


def refresh_token(user):
    return _encode(user, "refresh", timedelta(days=settings.JWT_REFRESH_DAYS))


def issue_tokens(user):
    return {"token": access_token(user), "refresh": refresh_token(user)}


def decode(token):
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise AuthenticationFailed("Token has expired.")
    except jwt.InvalidTokenError:
        raise AuthenticationFailed("Invalid token.")


def check_user(user, payload):
    """Shared checks for access and refresh tokens."""
    if not user.is_active:
        raise AuthenticationFailed("This account has been deactivated.")
    # Tokens issued before this feature have no `pv`; they simply expire.
    if "pv" in payload and payload["pv"] != password_version(user):
        raise AuthenticationFailed("Password was changed. Please log in again.")


def user_from_refresh(token):
    payload = decode(token)
    if payload.get("type") != "refresh":
        raise AuthenticationFailed("Not a refresh token.")
    if "sisuser_id" in payload:
        user = SisUser.objects.filter(id=payload["sisuser_id"]).first()
    else:
        user = User.objects.filter(id=payload.get("user_id")).first()
    if not user:
        raise AuthenticationFailed("Invalid token.")
    check_user(user, payload)
    return user
