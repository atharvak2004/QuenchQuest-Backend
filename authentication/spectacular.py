from drf_spectacular.extensions import OpenApiAuthenticationExtension
from authentication.sisuser_jwt_auth import SisUserJWTAuthentication
from authentication.jwt_auth import UserJWTAuthentication


class SisUserJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = SisUserJWTAuthentication
    name = "SisBearerAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
    

class UserJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = UserJWTAuthentication
    name = "UserBearerAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }