from collections import defaultdict
from datetime import timedelta
import hashlib

from django.core.cache import cache
from django.db.models import Count, Q
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
    ordering_fields = ('start_date', 'entry_close_at', 'created_at')
    ordering = ('-start_date',)  # most recent tournament date first by default

    def get_queryset(self):
        qs = (
            TournamentEdition.objects
            .select_related('tournament', 'tournament__organization', 'venue', 'data_source')
            .prefetch_related('categories__normalized_category', 'links')
            .annotate(categories_count=Count('categories'))
        )
        # Default: only show youth/junior tournaments.
        # is_youth=True  → classificado como juvenil → mostrar
        # is_youth=None  → ainda não classificado → mostrar (inclui acervo existente)
        # is_youth=False → explicitamente adulto  → ocultar
        # Pass ?youth_only=false to bypass this filter (admin use).
        youth_param = self.request.query_params.get('youth_only', 'true').lower()
        if youth_param != 'false':
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

        category_filter = Q(categories__normalized_category__taxonomy=PlayerCategory.TAXONOMY_OPEN)

        sporting_age = profile.sporting_age
        if sporting_age is not None:
            category_filter |= Q(
                categories__normalized_category__taxonomy__in=[
                    PlayerCategory.TAXONOMY_CBT_AGE,
                    PlayerCategory.TAXONOMY_FPT_AGE,
                    PlayerCategory.TAXONOMY_KIDS,
                ],
                categories__normalized_category__min_age__lte=sporting_age,
                categories__normalized_category__max_age__gte=sporting_age,
            )
            category_filter |= Q(
                categories__normalized_category__taxonomy=PlayerCategory.TAXONOMY_SENIORS,
                categories__normalized_category__min_age__lte=sporting_age,
            )

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

        if profile.gender:
            category_filter &= Q(
                categories__normalized_category__gender_scope__in=[profile.gender, '*', 'X']
            )

        return category_filter

    @action(detail=False, methods=['get'])
    def closing_soon(self, request):
        days = int(request.query_params.get('days', 14))
        now = timezone.now()
        end = now + timedelta(days=days)
        qs = self.get_queryset().filter(
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
        from apps.eligibility.location import within_profile_radius
        from apps.players.models import PlayerProfile

        profile_id = request.query_params.get('profile_id')
        if not profile_id:
            return Response({'error': 'profile_id e obrigatorio'}, status=400)

        try:
            profile = PlayerProfile.objects.get(pk=profile_id, user=request.user)
        except PlayerProfile.DoesNotExist:
            return Response({'error': 'Perfil nao encontrado'}, status=404)

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
            result = engine.evaluate_edition(edition)
            if result['compatible_count'] <= 0:
                continue
            if not within_profile_radius(profile, edition):
                continue
            data = self.get_serializer(edition).data
            data['eligibility'] = {
                'compatible_count': result['compatible_count'],
                'unknown_count': result['unknown_count'],
                'total_count': result['total_count'],
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
