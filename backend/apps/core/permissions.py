from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsAdminOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return request.user.is_authenticated and (
            request.user.is_staff or request.user.is_superuser
        )


class IsOwner(BasePermission):
    """Object-level: user owns the object."""
    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        if hasattr(obj, 'user_id'):
            return obj.user_id == request.user.id
        if hasattr(obj, 'user'):
            return obj.user_id == request.user.id
        return False


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.is_staff or request.user.is_superuser
        )


class IsSuperUser(BasePermission):
    """Acesso restrito ao master (superusuário). Admins comuns (staff) são barrados."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_superuser


class IsPartnerUser(BasePermission):
    """Acesso restrito à conta de parceiro (role=partner) com Partner vinculado e ativo.

    Garante o isolamento da área /parceiro: só atende quem tem login de parceiro,
    e as views devem sempre filtrar os dados por request.user.partner_account.
    """
    def has_permission(self, request, view):
        u = request.user
        if not (u.is_authenticated and getattr(u, 'role', '') == 'partner'):
            return False
        partner = getattr(u, 'partner_account', None)
        return partner is not None and partner.is_active
