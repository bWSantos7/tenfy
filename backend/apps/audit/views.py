from rest_framework import viewsets, serializers as rf_serializers
from apps.core.permissions import IsAdmin
from .models import AuditLog


class AuditLogSerializer(rf_serializers.ModelSerializer):
    actor_email = rf_serializers.CharField(source='actor.email', read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = (
            'id', 'actor', 'actor_email', 'action',
            'entity_type', 'entity_id', 'diff', 'reason',
            'ip_address', 'created_at',
        )


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.select_related('actor').all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAdmin]
    filterset_fields = ('action', 'entity_type', 'actor')
    search_fields = ('entity_id', 'reason')
