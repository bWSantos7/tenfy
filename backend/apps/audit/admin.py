from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'entity_type', 'entity_id', 'actor', 'created_at')
    list_filter = ('action', 'entity_type')
    search_fields = ('entity_id', 'actor__email', 'reason')
    readonly_fields = ('actor', 'action', 'entity_type', 'entity_id', 'diff', 'reason', 'ip_address', 'created_at', 'updated_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
