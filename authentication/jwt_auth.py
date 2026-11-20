from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import User
from .tokens import check_user
from .sisuser_jwt_auth import SisUserJWTAuthentication, decode_token, get_bearer_token  # noqa: F401


class UserJWTAuthentication(BaseAuthentication):
    """Authenticates volunteer (User) tokens issued by /api/auth/login/."""

    def authenticate(self, request):
        token = get_bearer_token(request)
        if not token:
            return None

        payload = decode_token(token)

        # Not a volunteer token (e.g. an admin/employee token) -> let the next authenticator try.
        if "user_id" not in payload:
            return None

        try:
            user = User.objects.get(id=payload["user_id"])
        except User.DoesNotExist:
            raise AuthenticationFailed("Invalid token.")

        check_user(user, payload)
        return (user, token)

    def authenticate_header(self, request):
        return "Bearer"
