from collections import defaultdict
from datetime import timedelta
import hashlib

from django.core.cache import cache
from django.db.models import Case, Count, ExpressionWrapper, IntegerField, Q, Value, When
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsAdmin
from apps.core.throttles import HeavyUserThrottle
from .filters import TournamentEditionFilter
from .models import Tournament, TournamentCategory, TournamentEdition
from .serializers import (
    TournamentCategorySerializer,
    TournamentEditionAdminSerializer,
    TournamentEditionDetailSerializer,
    TournamentEditionListSerializer,
    TournamentEditionSyncSerializer,
    TournamentSerializer,
)

_COMPATIBLE_CACHE_TTL = 300   # 5 minutes
_LIST_CACHE_TTL       = 120   # 2 minutes for public tournament list
_CALENDAR_CACHE_TTL   = 600   # 10 minutes for calendar (changes less often)


class TournamentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Tournament.objects.select_related('organization').all()
    serializer_class = TournamentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ('organization', 'modality', 'circuit')
    search_fields = ('canonical_name', 'canonical_slug', 'circuit')


class TournamentEditionViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    filterset_class = TournamentEditionFilter
    search_fields = ('title', 'tournament__canonical_name')
    ordering_fields = ('start_date', 'entry_close_at', 'created_at', 'status_priority')
    ordering = ('status_priority', 'start_date')

    @staticmethod
    def _build_dynamic_priority():
        """
        Replicates compute_dynamic_status() logic as a SQL annotation so ordering
        uses the live calculated status instead of the stored status field.
        Fixes cases where status='open' but dynamic_status='announced' or 'finished'.
        """
        now = timezone.now()
        today = now.date()
        soon = now + timedelta(days=3)
        # Q-based condition: status=open but no entry dates → announced priority
        open_no_dates = Q(status='open') & Q(entry_close_at__isnull=True) & Q(entry_open_at__isnull=True)
        return Case(
            When(status='canceled',          then=Value(5)),
            When(status='finished',          then=Value(4)),
            When(end_date__lt=today,         then=Value(4)),   # past end_date → finished
            When(start_date__lte=today,      then=Value(1)),   # started → in_progress
            When(entry_close_at__lt=now,     then=Value(2)),   # registrations closed
            When(entry_close_at__lte=soon,   then=Value(0)),   # closing in ≤3 days
            When(entry_close_at__isnull=False, then=Value(0)), # open with known deadline
            When(entry_open_at__lte=now,     then=Value(0)),   # registration period opened
            When(open_no_dates,              then=Value(1)),   # open status, no dates → announced
            default=Value(1),                                   # announced / unknown
            output_field=IntegerField(),
        )

    def get_queryset(self):
        qs = (
            TournamentEdition.objects
            .select_related('tournament', 'tournament__organization', 'venue', 'data_source')
            .prefetch_related('categories__normalized_category', 'links')
            .annotate(
                categories_count=Count('categories'),
                status_priority=self._build_dynamic_priority(),
            )
        )
        # Level-based filter: when player_level is provided (by frontend/mobile from the
        # active profile's competitive_level), it handles is_youth logic precisely.
        # Fall back to the generic youth_only filter when player_level is absent.
        #
        # is_youth=True  → classified as youth   → shown for 'youth' level
        # is_youth=None  → not yet classified     → shown by default (legacy data)
        # is_youth=False → explicitly adult        → hidden by default
        # Pass ?youth_only=false to bypass (admin use); ignored when player_level is set.
        player_level = self.request.query_params.get('player_level', '').strip()
        youth_param = self.request.query_params.get('youth_only', 'true').lower()
        if not player_level and youth_param != 'false':
            qs = qs.filter(Q(is_youth=True) | Q(is_youth__isnull=True))

        # Hide editions explicitly unpublished by admin from the public listing.
        # Admin endpoints (TournamentEditionAdminViewSet) bypass this.
        qs = qs.filter(is_published=True)
        return qs

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return TournamentEditionDetailSerializer
        return TournamentEditionListSerializer

    def _build_compatible_candidate_filter(self, profile):
        from apps.players.models import PlayerCategory

        # Always include OPEN categories
        category_filter = Q(categories__normalized_category__taxonomy=PlayerCategory.TAXONOMY_OPEN)

        # Always include editions that have unnormalized categories (COSAT, duplas, etc.)
        # The eligibility engine evaluates them via raw text extraction.
        category_filter |= Q(categories__normalized_category__isnull=True)

        sporting_age = profile.sporting_age
        if sporting_age is not None:
            # A player may enter any age category whose max_age >= their age.
            category_filter |= Q(
                categories__normalized_category__taxonomy__in=[
                    PlayerCategory.TAXONOMY_CBT_AGE,
                    PlayerCategory.TAXONOMY_FPT_AGE,
                    PlayerCategory.TAXONOMY_KIDS,
                ],
                categories__normalized_category__max_age__gte=sporting_age,
            )
            category_filter |= Q(
                categories__normalized_category__taxonomy=PlayerCategory.TAXONOMY_SENIORS,
                categories__normalized_category__min_age__lte=sporting_age,
            )

        # FPT class (informational — not a blocker, but still include as candidates)
        tennis_class = (profile.tennis_class or '').upper().strip()
        if tennis_class:
            if tennis_class == 'PR':
                category_filter |= Q(
                    categories__normalized_category__taxonomy=PlayerCategory.TAXONOMY_FPT_CLASS,
                    categories__normalized_category__class_level=5,
                )
            elif tennis_class.isdigit():
                player_class = int(tennis_class)
                allowed_levels = [player_class]
                if player_class > 1:
                    allowed_levels.append(player_class - 1)
                category_filter |= Q(
                    categories__normalized_category__taxonomy=PlayerCategory.TAXONOMY_FPT_CLASS,
                    categories__normalized_category__class_level__in=allowed_levels,
                )

        # Gender filter: allow match, wildcard, or unknown-gender normalized cats.
        # Do NOT apply gender filter globally — unnormalized categories handled by engine.
        if profile.gender:
            gender_q = Q(
                categories__normalized_category__gender_scope__in=[profile.gender, '*', 'X']
            ) | Q(categories__normalized_category__isnull=True)
            category_filter &= gender_q

        # Modality filter: if profile has preferred_modality set, only show tournaments
        # of that modality. This prevents beach_tennis appearing for tennis players, etc.
        preferred_modality = (profile.preferred_modality or '').strip()
        if preferred_modality:
            category_filter = Q(tournament__modality__iexact=preferred_modality) & category_filter

        return category_filter

    @action(detail=False, methods=['get'])
    def closing_soon(self, request):
        days = int(request.query_params.get('days', 14))
        now = timezone.now()
        end = now + timedelta(days=days)
        qs = self.filter_queryset(self.get_queryset()).filter(
            entry_close_at__isnull=False,
            entry_close_at__gte=now,
            entry_close_at__lte=end,
        ).exclude(
            status__in=[
                TournamentEdition.STATUS_CANCELED,
                TournamentEdition.STATUS_FINISHED,
            ]
        ).order_by('entry_close_at')
        page = self.paginate_queryset(qs)
        serializer = TournamentEditionListSerializer(page or qs, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def list(self, request, *args, **kwargs):
        """Override list() to add Redis cache for common queries."""
        import hashlib, json as _json
        params = dict(sorted(request.query_params.items()))
        cache_key = 'tournaments:list:' + hashlib.md5(_json.dumps(params).encode()).hexdigest()
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)
        response = super().list(request, *args, **kwargs)
        if response.status_code == 200:
            cache.set(cache_key, response.data, _LIST_CACHE_TTL)
        return response

    @action(detail=False, methods=['get'], throttle_classes=[HeavyUserThrottle])
    def calendar(self, request):
        import json as _json
        params = dict(sorted(request.query_params.items()))
        cache_key = 'tournaments:calendar:' + hashlib.md5(
            _json.dumps(params).encode()
        ).hexdigest()
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)
        qs = self.filter_queryset(self.get_queryset()).filter(start_date__isnull=False)
        buckets = defaultdict(list)
        for edition in qs[:500]:
            key = edition.start_date.strftime('%Y-%m')
            buckets[key].append(TournamentEditionListSerializer(edition).data)
        result = [{'month': key, 'items': value} for key, value in sorted(buckets.items())]
        cache.set(cache_key, result, _CALENDAR_CACHE_TTL)
        return Response(result)

    @action(detail=False, methods=['get'], throttle_classes=[HeavyUserThrottle])
    def compatible(self, request):
        from apps.eligibility.services import EligibilityEngine
        from apps.eligibility.location import within_profile_states, profile_state_result
        from apps.players.models import PlayerProfile

        profile_id = request.query_params.get('profile_id')
        if not profile_id:
            return Response({'error': 'profile_id e obrigatorio'}, status=400)

        try:
            profile = PlayerProfile.objects.get(pk=profile_id, user=request.user)
        except PlayerProfile.DoesNotExist:
            if request.user.role == 'parent':
                from apps.accounts.models import ParentChild
                child_ids = list(
                    ParentChild.objects.filter(parent=request.user, is_active=True)
                    .values_list('child_id', flat=True)
                )
                try:
                    profile = PlayerProfile.objects.get(pk=profile_id, user_id__in=child_ids)
                except PlayerProfile.DoesNotExist:
                    return Response({'error': 'Perfil não encontrado'}, status=404)
            else:
                return Response({'error': 'Perfil não encontrado'}, status=404)

        # Guard: profile without modality cannot produce safe results.
        # Without preferred_modality the category filter has no modality constraint,
        # which would mix tennis and beach_tennis editions in the same response.
        if not (profile.preferred_modality or '').strip():
            return Response(
                {
                    'error': 'Perfil sem modalidade definida.',
                    'detail': (
                        'Acesse o perfil esportivo e selecione a modalidade '
                        '(Tênis, Beach Tennis, etc.) para visualizar torneios compatíveis.'
                    ),
                    'code': 'modality_required',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache_key = 'compatible:{}:{}:{}'.format(
            request.user.id,
            profile.id,
            hashlib.sha256(request.get_full_path().encode()).hexdigest()[:16],
        )
        cached_payload = cache.get(cache_key)
        if cached_payload is not None:
            return Response(cached_payload)

        qs = self.filter_queryset(self.get_queryset()).exclude(
            status__in=[
                TournamentEdition.STATUS_CANCELED,
                TournamentEdition.STATUS_FINISHED,
            ]
        )
        category_filter = self._build_compatible_candidate_filter(profile)
        candidate_qs = qs.filter(category_filter).distinct().order_by('start_date', 'id')

        engine = EligibilityEngine(profile)
        compatible = []
        for edition in candidate_qs:
            # Location check using states (primary) — only exclude when explicitly outside
            loc = profile_state_result(profile, edition)
            if not loc['included']:
                continue

            result = engine.evaluate_edition(edition)
            # Include if any category is compatible, OR at least one unknown is
            # parseable (engine extracted age/gender but lacks profile data).
            # Purely unparseable categories (REASON_NOT_NORMALIZED) are not
            # sufficient on their own to qualify an edition as compatible.
            if result['compatible_count'] <= 0:
                continue

            data = self.get_serializer(edition).data
            data['eligibility'] = {
                'compatible_count': result['compatible_count'],
                'unknown_count': result['unknown_count'],
                'not_normalized_count': result.get('not_normalized_count', 0),
                'parseable_unknown_count': result['unknown_count'] - result.get('not_normalized_count', 0),
                'total_count': result['total_count'],
                'distance_status': loc['status'],
                'distance_message': loc['message'],
                'circuit_hint': result.get('circuit_hint'),
            }
            compatible.append(data)

        page = self.paginate_queryset(compatible)
        if page is not None:
            response = self.get_paginated_response(page)
            cache.set(cache_key, response.data, _COMPATIBLE_CACHE_TTL)
            return response

        payload = {'count': len(compatible), 'results': compatible}
        cache.set(cache_key, payload, _COMPATIBLE_CACHE_TTL)
        return Response(payload)

    @action(detail=False, methods=['post'])
    def check_conflicts(self, request):
        """RF-029: given a list of edition IDs, return all overlapping date pairs."""
        ids = request.data.get('ids', [])
        if not isinstance(ids, list) or len(ids) < 2:
            return Response({'detail': 'Envie pelo menos 2 IDs em "ids".'}, status=status.HTTP_400_BAD_REQUEST)
        if len(ids) > 10:
            return Response({'detail': 'Máximo de 10 IDs por requisição.'}, status=status.HTTP_400_BAD_REQUEST)

        editions = list(
            TournamentEdition.objects
            .filter(pk__in=ids)
            .only('id', 'title', 'start_date', 'end_date')
        )

        conflicts = []
        for i in range(len(editions)):
            for j in range(i + 1, len(editions)):
                a, b = editions[i], editions[j]
                a_start = a.start_date
                a_end = a.end_date or a.start_date
                b_start = b.start_date
                b_end = b.end_date or b.start_date
                if a_start is None or b_start is None:
                    continue
                # Overlaps when a starts before b ends and b starts before a ends
                if a_start <= b_end and b_start <= a_end:
                    conflicts.append({
                        'edition_a': {'id': a.id, 'title': a.title, 'start_date': str(a_start), 'end_date': str(a_end)},
                        'edition_b': {'id': b.id, 'title': b.title, 'start_date': str(b_start), 'end_date': str(b_end)},
                    })

        return Response({'conflicts': conflicts, 'has_conflicts': bool(conflicts)})

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        from .serializers import TournamentChangeEventSerializer

        edition = self.get_object()
        events = edition.change_events.all().order_by('-detected_at')[:100]
        return Response(TournamentChangeEventSerializer(events, many=True).data)

    @action(detail=True, methods=['patch'], url_path='sync-state')
    def sync_state(self, request, pk=None):
        """
        PATCH /api/tournaments/editions/{id}/sync-state/
        Called by n8n after successful entry sync to update needs_sync and last_synced_at.
        Auth: same as other tournament endpoints (IsAuthenticated).
        Accepts: needs_sync, last_synced_at, entries_source_url, candidate_entry_links,
                 sync_priority, parser_available, parser_limitation.
        """
        from apps.registrations.views import _check_import_auth
        if not (_check_import_auth(request) or request.user.is_staff):
            return Response(
                {'detail': 'Autenticação necessária.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        edition = self.get_object()
        serializer = TournamentEditionSyncSerializer(edition, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'detail': 'Sync state atualizado.', 'edition_id': edition.id})


class TournamentEditionAdminViewSet(viewsets.ModelViewSet):
    queryset = TournamentEdition.objects.all()
    serializer_class = TournamentEditionAdminSerializer
    permission_classes = [IsAdmin]

    def perform_update(self, serializer):
        serializer.save(
            reviewed_by=self.request.user,
            reviewed_at=timezone.now(),
            is_manual_override=True,
        )
        from apps.audit.models import AuditLog

        AuditLog.objects.create(
            actor=self.request.user,
            action=AuditLog.ACTION_UPDATE,
            entity_type='tournament_edition',
            entity_id=str(serializer.instance.id),
            diff={key: str(value) for key, value in serializer.validated_data.items()},
        )
