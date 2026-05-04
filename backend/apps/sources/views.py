from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Organization, DataSource
from .serializers import OrganizationSerializer, DataSourceSerializer
from apps.core.permissions import IsAdminOrReadOnly, IsAdmin


class OrganizationViewSet(viewsets.ModelViewSet):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    permission_classes = [IsAdminOrReadOnly]
    filterset_fields = ('type', 'state', 'is_active')
    search_fields = ('name', 'short_name')


class DataSourceViewSet(viewsets.ModelViewSet):
    queryset = DataSource.objects.select_related('organization').all()
    serializer_class = DataSourceSerializer
    filterset_fields = ('organization', 'source_type', 'enabled', 'priority')
    search_fields = ('source_name', 'slug', 'connector_key')

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [IsAdmin()]

    @action(detail=True, methods=['post'])
    def trigger(self, request, pk=None):
        from apps.ingestion.tasks import run_source
        source = self.get_object()
        result = run_source.delay(source.id)
        return Response({
            'detail': 'Ingestão disparada.',
            'task_id': result.id,
            'source_id': source.id,
        })

    @action(detail=True, methods=['post'])
    def toggle_enabled(self, request, pk=None):
        source = self.get_object()
        source.enabled = not source.enabled
        source.save(update_fields=['enabled', 'updated_at'])
        return Response({'id': source.id, 'enabled': source.enabled})
