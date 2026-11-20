from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import SisUser, User


class IsAdminUserRole(BasePermission):

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "choice", None) == "admin"
        )


class IsSisAdmin(BasePermission):

    def has_permission(self, request, view):
        return bool(
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


class IsVolunteerOrStaff(BasePermission):
    """Any logged-in volunteer (User) or admin/employee (SisUser)."""

    def has_permission(self, request, view):
        return isinstance(request.user, (User, SisUser))


class IsStaffOrReadOnlyAuthenticated(BasePermission):
    """Read: any logged-in volunteer/admin/employee. Write: admin/employee only."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return isinstance(request.user, (User, SisUser))
        return isinstance(request.user, SisUser) and request.user.choice in ["admin", "employee_role"]


class IsVolunteer(BasePermission):
    def has_permission(self, request, view):
        return isinstance(request.user, User)


class IsAnyStaff(BasePermission):
    """Any admin, employee or editor."""

    def has_permission(self, request, view):
        return isinstance(request.user, SisUser)


class HasModule(BasePermission):
    """Staff user whose role (or module_access) includes `view.module`."""

    message = "You don't have access to this part of the admin panel."

    def has_permission(self, request, view):
        module = getattr(view, "module", None)
        return isinstance(request.user, SisUser) and bool(module) and request.user.has_module(module)
