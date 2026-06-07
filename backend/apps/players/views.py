import logging
from datetime import timedelta

from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import PlayerProfile, PlayerCategory, PlayerProfileCategory
from .serializers import (
    PlayerProfileSerializer,
    PlayerCategorySerializer,
    PlayerProfileCategorySerializer,
)

logger = logging.getLogger('apps.players')


def _points_are_zero(points) -> bool:
    """
    True when a ranking points value represents zero / no standing.

    Handles Brazilian formatting ("0,00", "200,00", "3.440,00") and empty values.
    Empty/blank is treated as zero so entries without an actual standing are hidden.
    """
    s = str(points or '').strip()
    if not s:
        return True
    try:
        return float(s.replace('.', '').replace(',', '.')) == 0
    except ValueError:
        return False


_TI_CACHE_TTL = timedelta(hours=2)
_TI_SYNC_COOLDOWN = timedelta(minutes=30)
_UTR_SYNC_COOLDOWN = timedelta(minutes=30)


class PlayerProfileViewSet(viewsets.ModelViewSet):
    serializer_class = PlayerProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ('competitive_level', 'home_state', 'is_primary')

    def get_queryset(self):
        user = self.request.user

        if user.role == 'parent':
            from apps.accounts.models import ParentChild
            child_ids = list(
                ParentChild.objects.filter(parent=user, is_active=True).values_list('child_id', flat=True)
            )
            child_user_id = self.request.query_params.get('user_id')
            if child_user_id:
                try:
                    child_user_id_int = int(child_user_id)
                except (ValueError, TypeError):
                    child_user_id_int = None
                if child_user_id_int and child_user_id_int in child_ids:
                    child_ids = [child_user_id_int]

            return (
                PlayerProfile.objects
                .filter(user_id__in=child_ids)
                .prefetch_related('profile_categories__category')
                .order_by('user_id', '-is_primary', '-created_at')
            )

        return (
            PlayerProfile.objects
            .filter(user=user)
            .prefetch_related('profile_categories__category')
            .order_by('-is_primary', '-created_at')
        )

    def _is_managed_child(self):
        from apps.accounts.models import ParentChild
        return ParentChild.objects.filter(child=self.request.user, is_active=True).exists()

    def create(self, request, *args, **kwargs):
        if self._is_managed_child():
            if PlayerProfile.objects.filter(user=request.user).exists():
                return Response(
                    {'detail': 'Contas de filho não podem criar perfis esportivos adicionais. Peça ao responsável para gerenciar seus perfis.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
        elif request.user.role == 'parent':
            from apps.billing.models import Subscription
            current_count = PlayerProfile.objects.filter(user=request.user).count()
            try:
                sub = request.user.subscription
                max_dependent_profiles = sub.plan.max_members - 1
            except Subscription.DoesNotExist:
                max_dependent_profiles = 3
            if current_count >= max_dependent_profiles:
                return Response(
                    {'detail': f'Limite de {max_dependent_profiles} perfil(is) de dependentes atingido para o seu plano.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            # Jogador individual: máximo 1 perfil esportivo próprio.
            if PlayerProfile.objects.filter(user=request.user).exists():
                return Response(
                    {'detail': 'Jogadores individuais só podem ter um perfil esportivo.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        profile = serializer.save()
        from apps.registrations.tasks import (
            match_new_profile_to_entries, match_profile_now,
        )
        # Match imediato (síncrono) por external_id → inscrições/agenda na hora.
        try:
            match_profile_now(profile.pk)
        except Exception:  # noqa: BLE001 — nunca falhar a criação por causa do match
            logger.exception('match_profile_external_id_now failed for profile %s', profile.pk)
        # Match completo (fuzzy por nome) em background.
        match_new_profile_to_entries.delay(profile.pk)

    def destroy(self, request, *args, **kwargs):
        if self._is_managed_child():
            return Response(
                {'detail': 'Contas de filho não podem remover perfis esportivos.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        profile = self.get_object()
        if request.user.role == 'player':
            return Response(
                {'detail': 'Contas do tipo jogador devem manter o proprio perfil esportivo.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def set_primary(self, request, pk=None):
        if self._is_managed_child():
            return Response(
                {'detail': 'Contas de filho não podem alterar o perfil principal.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        profile = self.get_object()
        PlayerProfile.objects.filter(user=request.user, is_primary=True).update(is_primary=False)
        profile.is_primary = True
        profile.save(update_fields=['is_primary', 'updated_at'])
        return Response(PlayerProfileSerializer(profile).data)

    @action(detail=True, methods=['post'], url_path='categories')
    def add_category(self, request, pk=None):
        profile = self.get_object()
        category_id = request.data.get('category_id')
        is_primary = request.data.get('is_primary', False)
        if not category_id:
            return Response({'error': 'category_id obrigatório'}, status=400)
        category = get_object_or_404(PlayerCategory, pk=category_id)
        if is_primary:
            PlayerProfileCategory.objects.filter(
                profile=profile, is_primary=True
            ).update(is_primary=False)
        ppc, _ = PlayerProfileCategory.objects.update_or_create(
            profile=profile, category=category,
            defaults={'is_primary': is_primary},
        )
        return Response(PlayerProfileCategorySerializer(ppc).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], url_path='categories/(?P<category_id>[^/.]+)')
    def remove_category(self, request, pk=None, category_id=None):
        profile = self.get_object()
        PlayerProfileCategory.objects.filter(
            profile=profile, category_id=category_id
        ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ── Tênis Integrado ──────────────────────────────────────────────────────────

    @action(detail=True, methods=['get'], url_path='ti-data')
    def ti_data(self, request, pk=None):
        profile = self.get_object()

        from .parsers import extract_ti_id, TenisScrapeError
        ti_id, source = extract_ti_id(profile.external_ids or {})

        if not ti_id:
            return Response({
                'has_ti_id': False,
                'detail': 'Nenhum ID do Tênis Integrado vinculado a este perfil.',
                'results': [],
                'rankings': [],
                'catalog_rankings': [],
            })

        # Federation/CBT rankings imported into the local catalogue for this athlete.
        # Already kept fresh by the daily sync_ti_rankings_task — no scraping here.
        # Entries with zero points are not shown on the profile (athlete listed but
        # without an actual standing in that ranking).
        from .models import ExternalPlayerRanking
        from .serializers import ExternalPlayerRankingSerializer
        catalog_qs = (
            ExternalPlayerRanking.objects
            .filter(ti_player_id=str(ti_id))
            .order_by('source', 'ranking_name', 'category_label', 'position')
        )
        catalog_rankings = [
            r for r in ExternalPlayerRankingSerializer(catalog_qs, many=True).data
            if not _points_are_zero(r.get('points'))
        ]

        now = timezone.now()
        force_refresh = request.query_params.get('refresh') == '1'

        results_stale = (
            not profile.ti_results_synced_at
            or (now - profile.ti_results_synced_at) > _TI_CACHE_TTL
        )
        rankings_stale = (
            not profile.ti_rankings_synced_at
            or (now - profile.ti_rankings_synced_at) > _TI_CACHE_TTL
        )

        cache_empty = not profile.ti_results_cache and not profile.ti_rankings_cache
        if force_refresh or not profile.ti_results_synced_at or not profile.ti_rankings_synced_at or cache_empty:
            cooldown_ok = (
                not profile.ti_results_synced_at
                or (now - profile.ti_results_synced_at) > _TI_SYNC_COOLDOWN
            )
            if force_refresh and not cooldown_ok:
                return Response({
                    'has_ti_id': True,
                    'ti_id': ti_id,
                    'source': source,
                    'detail': 'Sincronização disponível em breve. Aguarde 30 minutos entre atualizações.',
                    'is_stale': results_stale or rankings_stale,
                    'results': profile.ti_results_cache or [],
                    'rankings': profile.ti_rankings_cache or [],
                    'catalog_rankings': catalog_rankings,
                    'results_synced_at': profile.ti_results_synced_at,
                    'rankings_synced_at': profile.ti_rankings_synced_at,
                }, status=status.HTTP_429_TOO_MANY_REQUESTS)

            _sync_ti_data_inline(profile, ti_id)
        elif results_stale or rankings_stale:
            try:
                from .tasks import sync_ti_data_task
                sync_ti_data_task.delay(profile.pk)
            except Exception:
                pass

        profile.refresh_from_db(fields=[
            'ti_results_cache', 'ti_rankings_cache',
            'ti_results_synced_at', 'ti_rankings_synced_at', 'ti_sync_error',
        ])

        return Response({
            'has_ti_id': True,
            'ti_id': ti_id,
            'source': source,
            'results_url': f'https://www.tenisintegrado.com.br/perfil2/jogos/{ti_id}',
            'rankings_url': f'https://www.tenisintegrado.com.br/perfil2/rankings/{ti_id}',
            'profile_url': f'https://www.tenisintegrado.com.br/perfil2/index/{ti_id}',
            'is_stale': results_stale or rankings_stale,
            'sync_error': profile.ti_sync_error or None,
            'results': profile.ti_results_cache or [],
            'rankings': profile.ti_rankings_cache or [],
            'catalog_rankings': catalog_rankings,
            'results_synced_at': profile.ti_results_synced_at,
            'rankings_synced_at': profile.ti_rankings_synced_at,
        })

    @action(detail=True, methods=['post'], url_path='ti-sync')
    def ti_sync(self, request, pk=None):
        profile = self.get_object()

        from .parsers import extract_ti_id
        ti_id, source = extract_ti_id(profile.external_ids or {})

        if not ti_id:
            return Response({'detail': 'Nenhum ID do Tênis Integrado vinculado.'}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        if profile.ti_results_synced_at and (now - profile.ti_results_synced_at) < _TI_SYNC_COOLDOWN:
            wait = int((_TI_SYNC_COOLDOWN - (now - profile.ti_results_synced_at)).total_seconds() / 60) + 1
            return Response(
                {'detail': f'Aguarde {wait} minuto(s) antes de sincronizar novamente.'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        _sync_ti_data_inline(profile, ti_id)
        profile.refresh_from_db(fields=[
            'ti_results_cache', 'ti_rankings_cache',
            'ti_results_synced_at', 'ti_rankings_synced_at', 'ti_sync_error',
        ])
        return Response({
            'detail': 'Dados sincronizados com sucesso.',
            'results_count': len(profile.ti_results_cache or []),
            'rankings_count': len(profile.ti_rankings_cache or []),
            'synced_at': profile.ti_results_synced_at,
            'sync_error': profile.ti_sync_error or None,
        })

    # ── UTR (Universal Tennis Rating) ────────────────────────────────────────────

    @action(detail=True, methods=['get'], url_path='utr-search')
    def utr_search(self, request, pk=None):
        """
        Search UTR public API by player name.
        GET /api/players/profiles/{id}/utr-search/?q=Julia+Nardy
        Returns up to 8 candidates with name, location, UTR singles/doubles.
        """
        self.get_object()  # permission / ownership check

        name = (request.query_params.get('q') or '').strip()
        if not name or len(name) < 2:
            return Response({'error': 'Informe pelo menos 2 caracteres no parâmetro q.'}, status=400)

        try:
            from .utr_service import search_utr_players
            candidates = search_utr_players(name)
            return Response({'candidates': candidates, 'query': name})
        except Exception as exc:
            logger.warning('UTR search error: %s', exc)
            return Response({'error': 'Não foi possível buscar na UTR. Tente novamente.'}, status=503)

    @action(detail=True, methods=['post'], url_path='utr-link')
    def utr_link(self, request, pk=None):
        """
        Confirm and store a UTR profile for this player profile.

        Body: { utr_player_id, display_name, singles_utr?, doubles_utr?, profile_url? }

        After saving the candidate data, tries to enrich ratings by calling the
        UTR player-detail API directly (fetch_utr_ratings_by_id), which is more
        reliable than the search API for some profiles.
        """
        profile = self.get_object()

        utr_player_id = str(request.data.get('utr_player_id') or '').strip()
        if not utr_player_id:
            return Response({'error': 'utr_player_id é obrigatório.'}, status=400)

        display_name = str(request.data.get('display_name') or '').strip()
        singles_utr  = str(request.data.get('singles_utr')  or '').strip()
        doubles_utr  = str(request.data.get('doubles_utr')  or '').strip()
        profile_url  = (
            str(request.data.get('profile_url') or '').strip()
            or f'https://app.utrsports.net/profiles/{utr_player_id}'
        )

        # No inline enrichment — the Celery task handles Playwright extraction

        profile.utr_player_id   = utr_player_id
        profile.utr_display_name = display_name
        profile.utr_singles      = singles_utr
        profile.utr_doubles      = doubles_utr
        profile.utr_profile_url  = profile_url
        profile.utr_synced_at    = timezone.now()
        profile.utr_sync_error   = ''
        profile.save(update_fields=[
            'utr_player_id', 'utr_display_name', 'utr_singles', 'utr_doubles',
            'utr_profile_url', 'utr_synced_at', 'utr_sync_error', 'updated_at',
        ])

        # Fire Celery task to open the profile in a headless browser and extract the real rating
        try:
            from .tasks import extract_utr_rating_task
            extract_utr_rating_task.delay(profile.pk)
        except Exception as exc:
            logger.warning('Could not enqueue UTR extraction task for profile=%s: %s', profile.pk, exc)

        return Response({
            'detail': 'Perfil UTR vinculado. Rating sendo extraído em segundo plano.',
            'utr_player_id':   profile.utr_player_id,
            'utr_display_name': profile.utr_display_name,
            'utr_singles':     profile.utr_singles,
            'utr_doubles':     profile.utr_doubles,
            'utr_profile_url': profile.utr_profile_url,
            'utr_synced_at':   profile.utr_synced_at,
        })

    @action(detail=True, methods=['post'], url_path='utr-unlink')
    def utr_unlink(self, request, pk=None):
        """Remove the UTR profile link from this player profile."""
        profile = self.get_object()
        profile.utr_player_id    = ''
        profile.utr_display_name = ''
        profile.utr_singles      = ''
        profile.utr_doubles      = ''
        profile.utr_profile_url  = ''
        profile.utr_synced_at    = None
        profile.utr_sync_error   = ''
        profile.save(update_fields=[
            'utr_player_id', 'utr_display_name', 'utr_singles', 'utr_doubles',
            'utr_profile_url', 'utr_synced_at', 'utr_sync_error', 'updated_at',
        ])
        return Response({'detail': 'Vínculo UTR removido.'})

    @action(detail=True, methods=['post'], url_path='utr-sync')
    def utr_sync(self, request, pk=None):
        """
        Refresh UTR rating for a linked profile.
        Strategy: try player-detail endpoint by ID first; fall back to search by name.
        Throttled to once per 30 min.
        """
        profile = self.get_object()

        if not profile.utr_player_id:
            return Response({'error': 'Nenhum perfil UTR vinculado.'}, status=400)

        now = timezone.now()
        if profile.utr_synced_at and (now - profile.utr_synced_at) < _UTR_SYNC_COOLDOWN:
            wait = int((_UTR_SYNC_COOLDOWN - (now - profile.utr_synced_at)).total_seconds() / 60) + 1
            return Response(
                {'error': f'Aguarde {wait} minuto(s) antes de sincronizar novamente.'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # Enqueue Playwright extraction task
        try:
            from .tasks import extract_utr_rating_task
            extract_utr_rating_task.delay(profile.pk)
            profile.utr_synced_at  = now
            profile.utr_sync_error = ''
            profile.save(update_fields=['utr_synced_at', 'utr_sync_error', 'updated_at'])
        except Exception as exc:
            logger.warning('Could not enqueue UTR extraction for profile=%s: %s', profile.pk, exc)
            return Response({'error': 'Falha ao sincronizar UTR. Tente novamente.'}, status=503)

        return Response({
            'detail': 'Sincronização em andamento. O rating será atualizado em instantes.',
            'utr_singles':    profile.utr_singles,
            'utr_doubles':    profile.utr_doubles,
            'utr_synced_at':  profile.utr_synced_at,
        })


def _sync_ti_data_inline(profile: PlayerProfile, ti_id: str):
    """Perform a synchronous TI data fetch and write results to the profile cache."""
    from .parsers import fetch_ti_results, fetch_ti_rankings, TenisScrapeError
    now = timezone.now()
    errors = []

    try:
        results = fetch_ti_results(ti_id)
        profile.ti_results_cache = results
        profile.ti_results_synced_at = now
    except TenisScrapeError as exc:
        errors.append(f'results: {exc}')
        logger.warning('TI results fetch failed profile=%s ti_id=%s: %s', profile.pk, ti_id, exc)

    try:
        rankings = fetch_ti_rankings(ti_id)
        profile.ti_rankings_cache = rankings
        profile.ti_rankings_synced_at = now
    except TenisScrapeError as exc:
        errors.append(f'rankings: {exc}')
        logger.warning('TI rankings fetch failed profile=%s ti_id=%s: %s', profile.pk, ti_id, exc)

    profile.ti_sync_error = '; '.join(errors)[:300] if errors else ''
    profile.save(update_fields=[
        'ti_results_cache', 'ti_rankings_cache',
        'ti_results_synced_at', 'ti_rankings_synced_at', 'ti_sync_error',
        'updated_at',
    ])


class PlayerCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PlayerCategory.objects.all()
    serializer_class = PlayerCategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ('taxonomy', 'gender_scope', 'class_level')
    search_fields = ('code', 'label_ptbr')
