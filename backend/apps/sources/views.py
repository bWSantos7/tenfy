from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Organization, DataSource
from .serializers import OrganizationSerializer, DataSourceSerializer
from apps.core.permissions import IsAdminOrReadOnly, IsAdmin


class _SilentJWTAuthentication:
    """
    JWT authentication that never raises AuthenticationFailed.
    Expired or malformed tokens are treated as anonymous requests instead of
    returning 401, which would break public read endpoints for logged-in users
    whose token has just expired (before the frontend auto-refreshes it).
    """
    def authenticate(self, request):
        try:
            from rest_framework_simplejwt.authentication import JWTAuthentication
            return JWTAuthentication().authenticate(request)
        except Exception:
            return None

    def authenticate_header(self, request):
        return 'Bearer'


class OrganizationViewSet(viewsets.ModelViewSet):
    serializer_class = OrganizationSerializer
    permission_classes = [IsAdminOrReadOnly]
    # Use silent JWT so an expired token doesn't return 401 on this public endpoint.
    # Invalid/expired tokens are treated as anonymous; valid tokens are honoured.
    authentication_classes = [_SilentJWTAuthentication]
    filterset_fields = ('type', 'state', 'is_active')
    search_fields = ('name', 'short_name')
    # No pagination: consumed as a flat array by the frontend filter dropdown.
    pagination_class = None

    def get_queryset(self):
        qs = Organization.objects.filter(is_active=True).order_by('short_name', 'name')
        # Non-admins only see orgs that have at least one tournament edition.
        if self.action == 'list' and not (
            self.request.user.is_staff or self.request.user.is_superuser
        ):
            qs = qs.filter(tournaments__editions__isnull=False).distinct()
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
