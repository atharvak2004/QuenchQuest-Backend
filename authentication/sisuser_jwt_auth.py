from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import SisUser
from .tokens import check_user, decode


def get_bearer_token(request):
    """Return the raw token from 'Authorization: Bearer <token>' (or a bare token)."""
    header = request.headers.get("Authorization")
    if not header:
        return None
    parts = header.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    if len(parts) == 1:
        return parts[0]
    raise AuthenticationFailed("Invalid Authorization header.")


def decode_token(token):
    payload = decode(token)
    if payload.get("type") == "refresh":
        raise AuthenticationFailed("Refresh tokens can't be used to call the API.")
    return payload


class SisUserJWTAuthentication(BaseAuthentication):
    """Authenticates admin/employee/editor (SisUser) tokens from /api/auth/sisuser/login/."""

    def authenticate(self, request):
        token = get_bearer_token(request)
        if not token:
            return None

        payload = decode_token(token)

        # Not a SisUser token (e.g. a volunteer token) -> let the next authenticator try.
        if "sisuser_id" not in payload:
            return None

        try:
            user = SisUser.objects.get(id=payload["sisuser_id"])
        except SisUser.DoesNotExist:
            raise AuthenticationFailed("Invalid token.")

        check_user(user, payload)
        return (user, token)

    def authenticate_header(self, request):
        return "Bearer"
