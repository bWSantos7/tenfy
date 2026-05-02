"""
Admin panel: consolidated endpoints used by the admin web UI:
- Dashboard counters
- Review queue (low-confidence / recently changed / missing-link editions)
- User management (list, edit, delete)
- Statistics (time-series charts)
- Edition inline patch (manual override / confidence update)
- Data source management
"""
from datetime import timedelta, date
from django.contrib.auth import get_user_model
from django.db.models import Q, Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.core.permissions import IsAdmin
from apps.tournaments.models import TournamentEdition
from apps.sources.models import DataSource, Organization
from apps.ingestion.models import IngestionRun
from apps.audit.models import AuditLog
from apps.alerts.models import Alert
from apps.tournaments.serializers import TournamentEditionListSerializer

User = get_user_model()


class AdminUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            'id', 'email', 'full_name', 'phone', 'role',
            'is_active', 'is_staff', 'is_superuser',
            'email_verified',
            'marketing_consent', 'created_at', 'last_login',
        )
        read_only_fields = ('id', 'email', 'created_at', 'last_login', 'is_superuser')


@api_view(['GET'])
@permission_classes([IsAdmin])
def user_list(request):
    """List all users with optional search."""
    qs = User.objects.order_by('-created_at')
    q = request.query_params.get('q', '').strip()
    if q:
        qs = qs.filter(Q(email__icontains=q) | Q(full_name__icontains=q))
    return Response(AdminUserSerializer(qs, many=True).data)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAdmin])
def user_detail(request, pk):
    """Edit or delete a single user. Cannot act on your own account."""
    try:
        user = User.objects.get(pk=pk)
    except User.DoesNotExist:
        return Response({'detail': 'Usuário não encontrado.'}, status=status.HTTP_404_NOT_FOUND)

    if user.pk == request.user.pk:
        return Response({'detail': 'Você não pode editar ou deletar sua própria conta aqui.'}, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'DELETE':
        if user.is_superuser:
            return Response({'detail': 'Não é possível deletar um superusuário.'}, status=status.HTTP_400_BAD_REQUEST)
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # PATCH
    ser = AdminUserSerializer(user, data=request.data, partial=True)
    ser.is_valid(raise_exception=True)
    # Prevent promoting to superuser via API
    ser.save(is_superuser=user.is_superuser)
    return Response(ser.data)


@api_view(['GET'])
@permission_classes([IsAdmin])
def dashboard(request):
    now = timezone.now()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    editions_qs = TournamentEdition.objects.all()
    youth_qs = editions_qs.filter(Q(is_youth=True) | Q(is_youth__isnull=True))
    return Response({
        'counts': {
            'tournaments_total': youth_qs.count(),
            'tournaments_open': youth_qs.filter(status=TournamentEdition.STATUS_OPEN).count(),
            'tournaments_closing_soon': youth_qs.filter(
                status__in=[
                    TournamentEdition.STATUS_CLOSING_SOON,
                    TournamentEdition.STATUS_OPEN,
                ],
                entry_close_at__gt=now,
                entry_close_at__lt=now + timedelta(days=7),
            ).count(),
            'data_sources_enabled': DataSource.objects.filter(enabled=True).count(),
            'data_sources_total': DataSource.objects.count(),
            'manual_overrides': youth_qs.filter(is_manual_override=True).count(),
            'low_confidence': youth_qs.filter(
                data_confidence=TournamentEdition.CONFIDENCE_LOW
            ).count(),
            'missing_official_url': youth_qs.filter(
                Q(official_source_url='') | Q(official_source_url__isnull=True)
            ).count(),
        },
        'ingestion': {
            'runs_24h': IngestionRun.objects.filter(started_at__gte=last_24h).count(),
            'failed_24h': IngestionRun.objects.filter(
                started_at__gte=last_24h, status=IngestionRun.STATUS_FAILED
            ).count(),
            'partial_24h': IngestionRun.objects.filter(
                started_at__gte=last_24h, status=IngestionRun.STATUS_PARTIAL
            ).count(),
        },
        'alerts': {
            'total_7d': Alert.objects.filter(created_at__gte=last_7d).count(),
            'failed_7d': Alert.objects.filter(
                created_at__gte=last_7d, status=Alert.STATUS_FAILED
            ).count(),
        },
        'audit': {
            'actions_24h': AuditLog.objects.filter(created_at__gte=last_24h).count(),
        },
    })


@api_view(['GET'])
@permission_classes([IsAdmin])
def stats(request):
    """Platform statistics for charts."""
    now = timezone.now()
    days = int(request.query_params.get('days', 30))
    since = now - timedelta(days=days)

    # Daily new registrations
    reg_qs = (
        User.objects
        .filter(created_at__gte=since)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(count=Count('id'))
        .order_by('day')
    )
    reg_by_day = {str(r['day']): r['count'] for r in reg_qs}
    all_days = [(since.date() + timedelta(days=i)).isoformat() for i in range(days + 1)]
    registrations = [{'date': d, 'registrations': reg_by_day.get(d, 0)} for d in all_days]

    # Users by role
    roles = (
        User.objects
        .values('role')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    role_labels = {'player': 'Jogador', 'coach': 'Treinador', 'parent': 'Pai/Resp.', 'admin': 'Admin'}
    users_by_role = [{'role': role_labels.get(r['role'], r['role']), 'count': r['count']} for r in roles]

    # Tournaments by status
    from apps.tournaments.models import TournamentEdition
    status_qs = (
        TournamentEdition.objects
        .values('status')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    status_labels = {
        'open': 'Aberto', 'closing_soon': 'Fechando', 'closed': 'Encerrado',
        'in_progress': 'Em andamento', 'finished': 'Finalizado',
        'announced': 'Anunciado', 'canceled': 'Cancelado', 'unknown': 'Desconhecido',
        'draws_published': 'Chaves pub.',
    }
    tournaments_by_status = [
        {'status': status_labels.get(s['status'], s['status']), 'count': s['count']}
        for s in status_qs
    ]

    # Watchlist items by user_status
    from apps.watchlist.models import WatchlistItem
    wl_qs = (
        WatchlistItem.objects
        .values('user_status')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    wl_labels = {
        'none': 'Nenhum', 'intended': 'Pretende', 'registered_declared': 'Inscrito',
        'withdrawn': 'Desistiu', 'completed': 'Concluído',
    }
    watchlist_by_status = [
        {'status': wl_labels.get(w['user_status'], w['user_status']), 'count': w['count']}
        for w in wl_qs
    ]

    return Response({
        'registrations': registrations,
        'users_by_role': users_by_role,
        'tournaments_by_status': tournaments_by_status,
        'watchlist_by_status': watchlist_by_status,
        'totals': {
            'users': User.objects.count(),
            'active_users': User.objects.filter(is_active=True).count(),
            'new_users_period': User.objects.filter(created_at__gte=since).count(),
        },
    })


@api_view(['GET'])
@permission_classes([IsAdmin])
def review_queue(request):
    """Editions that need human curation."""
    from apps.tournaments.models import TournamentChangeEvent

    base_qs = TournamentEdition.objects.select_related(
        'tournament__organization', 'venue', 'data_source'
    ).prefetch_related('categories__normalized_category', 'links')

    low_conf = base_qs.filter(
        data_confidence=TournamentEdition.CONFIDENCE_LOW,
        is_manual_override=False,
    ).order_by('-fetched_at')[:20]

    no_link = base_qs.filter(
        Q(official_source_url='') | Q(official_source_url__isnull=True),
        is_manual_override=False,
    ).order_by('-fetched_at')[:20]

    cutoff = timezone.now() - timedelta(days=2)
    recent_ids = (
        TournamentChangeEvent.objects
        .filter(detected_at__gte=cutoff)
        .values_list('edition_id', flat=True)
        .distinct()[:20]
    )
    recently_changed = base_qs.filter(id__in=list(recent_ids)).order_by('-updated_at')

    return Response({
        'low_confidence': TournamentEditionListSerializer(low_conf, many=True).data,
        'missing_official_url': TournamentEditionListSerializer(no_link, many=True).data,
        'recently_changed': TournamentEditionListSerializer(recently_changed, many=True).data,
    })


class EditionPatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = TournamentEdition
        fields = (
            'id', 'title', 'status', 'start_date', 'end_date',
            'entry_open_at', 'entry_close_at', 'official_source_url',
            'base_price_brl', 'data_confidence', 'is_manual_override', 'is_youth',
            'is_published',
        )
        read_only_fields = ('id',)


class AdminEditionListSerializer(serializers.ModelSerializer):
    """Compact list serializer for the admin editions tab.
    Includes is_published and curation flags so admin can see hidden items."""
    organization_short_name = serializers.CharField(source='tournament.organization.short_name', read_only=True)
    venue_city = serializers.CharField(source='venue.city', read_only=True, default='')
    venue_state = serializers.CharField(source='venue.state', read_only=True, default='')

    class Meta:
        model = TournamentEdition
        fields = (
            'id', 'title', 'status',
            'start_date', 'end_date', 'entry_close_at',
            'data_confidence', 'is_manual_override', 'is_youth', 'is_published',
            'official_source_url', 'source_name',
            'organization_short_name', 'venue_city', 'venue_state',
        )


@api_view(['GET'])
@permission_classes([IsAdmin])
def admin_editions_list(request):
    """
    Admin-only listing of TournamentEdition that INCLUDES unpublished items.
    Supports query params:
      - q          → text search across title / org / venue
      - published  → 'true' | 'false' to filter; omit for all
      - youth_only → 'true' (default off — admin needs to see everything)
      - page_size  → default 30 (cap 200)
    """
    qs = (
        TournamentEdition.objects
        .select_related('tournament__organization', 'venue')
        .order_by('-start_date', '-id')
    )

    q = request.query_params.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(title__icontains=q)
            | Q(tournament__canonical_name__icontains=q)
            | Q(tournament__organization__short_name__icontains=q)
            | Q(venue__name__icontains=q)
            | Q(venue__city__icontains=q)
        )

    published = request.query_params.get('published')
    if published is not None:
        if published.lower() in ('1', 'true', 'yes'):
            qs = qs.filter(is_published=True)
        elif published.lower() in ('0', 'false', 'no'):
            qs = qs.filter(is_published=False)

    if request.query_params.get('youth_only', 'false').lower() == 'true':
        qs = qs.filter(Q(is_youth=True) | Q(is_youth__isnull=True))

    try:
        page_size = min(int(request.query_params.get('page_size', 30)), 200)
    except ValueError:
        page_size = 30

    total = qs.count()
    items = qs[:page_size]
    return Response({
        'count': total,
        'results': AdminEditionListSerializer(items, many=True).data,
    })


class EditionCreateSerializer(serializers.ModelSerializer):
    """Serializer for manually creating a tournament edition in the admin panel."""
    circuit = serializers.CharField(required=True)
    venue_city = serializers.CharField(required=False, allow_blank=True)
    venue_state = serializers.CharField(required=False, allow_blank=True, max_length=2)

    class Meta:
        model = TournamentEdition
        fields = (
            'title', 'circuit', 'status', 'start_date', 'end_date',
            'entry_open_at', 'entry_close_at', 'official_source_url',
            'base_price_brl', 'is_youth',
            'venue_city', 'venue_state',
        )

    def create(self, validated_data):
        from apps.sources.models import Organization
        from apps.tournaments.models import Tournament, Venue
        city = validated_data.pop('venue_city', '')
        state = validated_data.pop('venue_state', '')
        circuit = validated_data.pop('circuit')

        # Get or create org for manual entries
        org, _ = Organization.objects.get_or_create(
            short_name=circuit,
            defaults={'name': circuit, 'type': 'platform'},
        )

        # Get or create the tournament identity
        import re, unicodedata
        title = validated_data.get('title', '')
        slug = re.sub(r'[^a-z0-9]+', '-', unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode().lower()).strip('-')[:200]
        tournament, _ = Tournament.objects.get_or_create(
            canonical_slug=slug,
            defaults={'canonical_name': title, 'organization': org, 'circuit': circuit},
        )

        # Venue
        venue = None
        if city or state:
            venue, _ = Venue.objects.get_or_create(
                city=city, state=state,
                defaults={'name': f'{city} - {state}' if city and state else (city or state)},
            )

        # Note: `circuit` is part of the Tournament model (already set above
        # via Tournament.objects.get_or_create defaults), not TournamentEdition.
        edition = TournamentEdition.objects.create(
            tournament=tournament,
            venue=venue,
            source_name='manual',
            data_confidence=TournamentEdition.CONFIDENCE_HIGH,
            is_manual_override=True,
            season_year=validated_data.get('start_date', date.today()).year if validated_data.get('start_date') else date.today().year,
            **validated_data,
        )
        return edition


@api_view(['POST'])
@permission_classes([IsAdmin])
def edition_create(request):
    """
    Manually create a tournament edition — for COSAT/ITF/UTR entries
    that cannot be fetched automatically due to connector blocks.
    """
    ser = EditionCreateSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    edition = ser.save()
    from apps.tournaments.serializers import TournamentEditionListSerializer
    return Response(TournamentEditionListSerializer(edition).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAdmin])
def connector_status(request):
    """
    Return status of each registered connector — last run, last status,
    consecutive failures, and whether it's currently blocked (circuit open).
    """
    from django.core.cache import cache
    from apps.ingestion.connectors import registered_connectors

    result = []
    sources = {ds.connector_key: ds for ds in DataSource.objects.select_related('organization').all()}

    for key in sorted(registered_connectors().keys()):
        ds = sources.get(key)
        cb_open = bool(cache.get(f'asaas:cb:open'))  # reuse pattern for ingestion if added later
        # Per-connector circuit breaker keys
        failures_key = f'connector:failures:{key}'
        open_key = f'connector:open:{key}'
        is_blocked = bool(cache.get(open_key))
        consecutive_failures = cache.get(failures_key, 0)

        result.append({
            'connector_key': key,
            'enabled': ds.enabled if ds else False,
            'source_name': ds.source_name if ds else key,
            'organization': ds.organization.short_name if ds else '—',
            'last_run_at': ds.last_run_at.isoformat() if ds and ds.last_run_at else None,
            'last_run_status': ds.last_run_status if ds else None,
            'is_blocked': is_blocked,
            'consecutive_failures': consecutive_failures,
            'action': 'Curar manualmente' if is_blocked else ('Ingerir' if ds and ds.enabled else 'Desativado'),
        })

    return Response(result)


@api_view(['PATCH'])
@permission_classes([IsAdmin])
def edition_patch(request, pk):
    """Inline admin edit for a TournamentEdition (manual override / curation)."""
    try:
        edition = TournamentEdition.objects.get(pk=pk)
    except TournamentEdition.DoesNotExist:
        return Response({'detail': 'Edição não encontrada.'}, status=status.HTTP_404_NOT_FOUND)

    ser = EditionPatchSerializer(edition, data=request.data, partial=True)
    ser.is_valid(raise_exception=True)
    instance = ser.save(
        reviewed_at=timezone.now(),
        reviewed_by=request.user,
        is_manual_override=True,
    )
    # Return the patched fields (including is_published) plus list metadata.
    patched = EditionPatchSerializer(instance).data
    listed = TournamentEditionListSerializer(instance).data
    return Response({**listed, **patched})


class DataSourceSerializer(serializers.ModelSerializer):
    org_name = serializers.CharField(source='organization.short_name', read_only=True)

    class Meta:
        model = DataSource
        fields = (
            'id', 'organization', 'org_name', 'source_name', 'slug',
            'connector_key', 'source_type', 'base_url',
            'fetch_schedule_cron', 'priority', 'enabled',
            'legal_notes', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')


@api_view(['GET'])
@permission_classes([IsAdmin])
def data_sources_list(request):
    """List all data sources with optional filter by enabled status."""
    qs = DataSource.objects.select_related('organization').order_by('organization__short_name', 'priority')
    enabled = request.query_params.get('enabled')
    if enabled is not None:
        qs = qs.filter(enabled=enabled.lower() in ('1', 'true', 'yes'))
    return Response(DataSourceSerializer(qs, many=True).data)


@api_view(['GET'])
@permission_classes([IsAdmin])
def execution_logs(request):
    """Return recent ingestion runs with timestamps, status, errors and service info."""
    limit = min(int(request.query_params.get('limit', 50)), 200)
    runs = (
        IngestionRun.objects
        .select_related('data_source__organization')
        .order_by('-started_at')[:limit]
    )
    data = []
    for run in runs:
        data.append({
            'id': run.id,
            'started_at': run.started_at.isoformat() if run.started_at else None,
            'finished_at': run.finished_at.isoformat() if run.finished_at else None,
            'duration_seconds': (
                int((run.finished_at - run.started_at).total_seconds())
                if run.finished_at and run.started_at else None
            ),
            'status': run.status,
            'service': run.data_source.source_name if run.data_source else 'manual',
            'organization': run.data_source.organization.short_name if run.data_source and run.data_source.organization else '—',
            'editions_found': run.items_fetched,
            'editions_created': run.items_created,
            'editions_updated': run.items_updated,
            'error': run.error_summary or '',
        })
    return Response(data)


@api_view(['PATCH'])
@permission_classes([IsAdmin])
def data_source_patch(request, pk):
    """Toggle or update a data source configuration."""
    try:
        source = DataSource.objects.get(pk=pk)
    except DataSource.DoesNotExist:
        return Response({'detail': 'Fonte não encontrada.'}, status=status.HTTP_404_NOT_FOUND)

    allowed_fields = {'enabled', 'fetch_schedule_cron', 'priority', 'legal_notes', 'base_url'}
    patch_data = {k: v for k, v in request.data.items() if k in allowed_fields}
    ser = DataSourceSerializer(source, data=patch_data, partial=True)
    ser.is_valid(raise_exception=True)
    ser.save()
    return Response(ser.data)


@api_view(['GET'])
@permission_classes([IsAdmin])
def ingestion_runs_list(request):
    """Recent ingestion runs (last 50)."""
    qs = (
        IngestionRun.objects
        .select_related('data_source__organization')
        .order_by('-started_at')[:50]
    )

    class RunSerializer(serializers.ModelSerializer):
        source_name = serializers.CharField(source='data_source.source_name', read_only=True)
        org_name = serializers.CharField(source='data_source.organization.short_name', read_only=True)

        class Meta:
            model = IngestionRun
            fields = (
                'id', 'source_name', 'org_name', 'status',
                'started_at', 'finished_at',
                'items_fetched', 'items_created', 'items_updated', 'changes_detected',
                'error_summary',
            )

    return Response(RunSerializer(qs, many=True).data)
