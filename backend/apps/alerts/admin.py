from django.contrib import admin
from .models import Alert, UserAlertPreference


@admin.register(UserAlertPreference)
class UserAlertPreferenceAdmin(admin.ModelAdmin):
    list_display = ('user', 'email_enabled', 'in_app_enabled', 'changes_enabled', 'draws_enabled')
    search_fields = ('user__email',)


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'kind', 'channel', 'status', 'dispatched_at', 'created_at')
    list_filter = ('kind', 'channel', 'status')
    search_fields = ('user__email', 'title', 'body')
    readonly_fields = ('created_at', 'updated_at', 'dispatched_at', 'read_at')
