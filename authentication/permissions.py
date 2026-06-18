from rest_framework.permissions import BasePermission
from .models import *

class IsAdminUserRole(BasePermission):

    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.choice == "admin"
        )


class IsSisAdmin(BasePermission):

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and isinstance(request.user, SisUser)
            and request.user.choice == "admin"
        )
    
class IsEmployeeOrAdmin(BasePermission):

    def has_permission(self, request, view):
        return (
            isinstance(request.user, SisUser)
            and request.user.choice in ["admin", "employee_role"]
        )    