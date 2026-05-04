from rest_framework import serializers
from .models import Alert, UserAlertPreference


class AlertSerializer(serializers.ModelSerializer):
    edition_title = serializers.CharField(source='edition.title', read_only=True, default=None)
    edition_start_date = serializers.DateField(source='edition.start_date', read_only=True, default=None)
    edition_official_url = serializers.URLField(source='edition.official_source_url', read_only=True, default=None)

    class Meta:
        model = Alert
        fields = (
            'id', 'kind', 'channel', 'status',
            'title', 'body', 'payload',
            'edition', 'edition_title', 'edition_start_date', 'edition_official_url',
            'dispatched_at', 'read_at', 'dedup_key',
            'created_at',
        )
        read_only_fields = fields


class UserAlertPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserAlertPreference
        fields = (
            'in_app_enabled', 'push_enabled',
            'deadline_days', 'changes_enabled', 'draws_enabled',
        )

    def update(self, instance, validated_data):
        instance.email_enabled = False
        return super().update(instance, validated_data)
