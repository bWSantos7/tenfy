from django.contrib import admin
from .models import Organization, DataSource


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'short_name', 'type', 'state', 'is_active')
    list_filter = ('type', 'state', 'is_active')
    search_fields = ('name', 'short_name')


@admin.register(DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    list_display = ('source_name', 'organization', 'source_type', 'enabled', 'priority', 'last_run_at', 'last_run_status')
    list_filter = ('source_type', 'enabled', 'priority', 'organization')
    search_fields = ('source_name', 'slug', 'connector_key')
    readonly_fields = ('last_run_at', 'last_run_status', 'created_at', 'updated_at')
