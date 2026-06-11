from django.db.models import Q
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
        # Non-admins only see orgs que têm torneios E são entidades oficiais do
        # filtro: federações estaduais com UF (as 27) + conectores nacionais/
        # internacionais (CBT/COSAT/ITF/UTR). Exclui orgs sem UF (ex.: beach
        # tennis) e plataformas fora dessa lista.
        if self.action == 'list' and not (
            self.request.user.is_staff or self.request.user.is_superuser
        ):
            official = (
                (Q(type=Organization.TYPE_FEDERATION) & ~Q(state=''))
                | Q(short_name__in=['CBT', 'COSAT', 'ITF', 'UTR'])
            )
            qs = qs.filter(official).filter(
                tournaments__editions__isnull=False).distinct()
        return qs

    @action(detail=False, methods=['get'])
    def federations(self, request):
        """
        GET /api/sources/organizations/federations/

        Flat list of state federations for the profile/onboarding picker, ordered
        by UF. Unlike the default `list` action, this is NOT filtered by tournament
        editions — every federation must be selectable even without synced
        tournaments.

        Deduplicated by UF: production may hold more than one federation org per
        state (e.g. an accented canonical row and an ingestion-created unaccented
        one). We expose a single entry per UF, preferring the canonical name from
        apps.sources.federations so the label is clean. Eligibility matches by UF,
        so which duplicate a profile points to does not affect compatibility.
        """
        from apps.sources.federations import BRAZIL_TENNIS_FEDERATIONS

        canonical_name_by_uf = {uf: name for uf, name, _short in BRAZIL_TENNIS_FEDERATIONS}

        qs = (
            Organization.objects
            .filter(is_active=True, type=Organization.TYPE_FEDERATION)
            .order_by('state', 'id')
        )

        by_uf: dict[str, Organization] = {}
        stateless: list[Organization] = []
        for org in qs:
            uf = (org.state or '').upper()
            if not uf:
                stateless.append(org)
                continue
            current = by_uf.get(uf)
            if current is None:
                by_uf[uf] = org
            elif org.name == canonical_name_by_uf.get(uf) and current.name != canonical_name_by_uf.get(uf):
                # Prefer the canonical-named org for the picker label.
                by_uf[uf] = org

        deduped = sorted(by_uf.values(), key=lambda o: o.state) + stateless
        return Response(OrganizationSerializer(deduped, many=True).data)


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
