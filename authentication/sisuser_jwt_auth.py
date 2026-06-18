import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import SisUser

class SisUserJWTAuthentication(BaseAuthentication):

    def authenticate(self, request):

      token = request.headers.get("Authorization")

      if not token:
        return None

      if token.startswith("Bearer "):
        token = token.split(" ")[1]

      try:
          payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"]
          )

          user = SisUser.objects.get(
            id=payload["sisuser_id"]
         )

      except Exception:
        raise AuthenticationFailed("Invalid token")

      return (user, token)
