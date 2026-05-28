from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Organization, DataSource
from .serializers import OrganizationSerializer, DataSourceSerializer
from apps.core.permissions import IsAdminOrReadOnly, IsAdmin


class OrganizationViewSet(viewsets.ModelViewSet):
    serializer_class = OrganizationSerializer
    permission_classes = [IsAdminOrReadOnly]
    filterset_fields = ('type', 'state', 'is_active')
    search_fields = ('name', 'short_name')
    # No pagination: this is a reference list consumed as a flat array by the
    # frontend filter dropdowns. Global pagination would break listOrganizations().
    pagination_class = None

    def get_queryset(self):
        qs = Organization.objects.filter(is_active=True).order_by('short_name', 'name')
        # For the public list action, return only orgs that have at least one
        # tournament so the filter dropdown doesn't show unused entries.
        if self.action == 'list' and not (
            self.request.user.is_staff or self.request.user.is_superuser
        ):
            qs = qs.filter(tournaments__isnull=False).distinct()
        return qs


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
