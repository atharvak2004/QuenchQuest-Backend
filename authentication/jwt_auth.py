import jwt

from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from authentication.models import User 
from .models import User
from .models import SisUser

class UserJWTAuthentication(BaseAuthentication):

    def authenticate(self, request):

        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return None

        try:
            token = auth_header.split(" ")[1]

            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=["HS256"]
            )

            user = User.objects.get(id=payload["user_id"])

            return (user, None)

        except Exception:
            raise AuthenticationFailed(
                "Invalid or expired token"
            )
        


class SisUserJWTAuthentication(BaseAuthentication):

    def authenticate(self, request):

        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return None

        try:
            token = auth_header.split(" ")[1]

            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=["HS256"]
            )

            user = SisUser.objects.get(id=payload["user_id"])

            return (user, None)

        except Exception:
            raise AuthenticationFailed("Invalid or expired token")        