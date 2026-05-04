from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import ParentChild, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'full_name', 'role', 'is_staff', 'is_active', 'created_at')
    list_filter = ('role', 'is_staff', 'is_active', 'created_at')
    search_fields = ('email', 'full_name')
    ordering = ('-created_at',)
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Perfil', {'fields': ('full_name', 'role')}),
        ('Privacidade', {'fields': ('consent_version', 'consented_at', 'marketing_consent')}),
        ('Permissões', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Datas', {'fields': ('last_login', 'created_at', 'updated_at', 'last_login_ip')}),
    )
    add_fieldsets = (
        (None, {'classes': ('wide',), 'fields': ('email', 'password1', 'password2', 'role')}),
    )
    readonly_fields = ('last_login', 'created_at', 'updated_at', 'last_login_ip', 'consented_at')


@admin.register(ParentChild)
class ParentChildAdmin(admin.ModelAdmin):
    list_display = ('parent', 'child', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('parent__email', 'parent__full_name', 'child__email', 'child__full_name')
    autocomplete_fields = ('parent', 'child')
