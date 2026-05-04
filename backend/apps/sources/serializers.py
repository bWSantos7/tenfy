from rest_framework import serializers
from .models import Organization, DataSource


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = (
            'id', 'name', 'short_name', 'type', 'website_url', 'logo_url',
            'state', 'description', 'is_active', 'created_at'
        )


class DataSourceSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    organization_short = serializers.CharField(source='organization.short_name', read_only=True)

    class Meta:
        model = DataSource
        fields = (
            'id', 'organization', 'organization_name', 'organization_short',
            'source_name', 'slug', 'source_type', 'base_url', 'connector_key',
            'fetch_schedule_cron', 'enabled', 'priority', 'legal_notes',
            'config_json', 'last_run_at', 'last_run_status',
            'created_at', 'updated_at',
        )
        read_only_fields = ('last_run_at', 'last_run_status', 'created_at', 'updated_at')
