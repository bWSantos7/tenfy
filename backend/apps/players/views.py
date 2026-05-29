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

_TI_CACHE_TTL = timedelta(hours=2)    # serve from cache if younger than this
_TI_SYNC_COOLDOWN = timedelta(minutes=30)  # min interval between forced re-syncs


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
            # Optional filter: parent requesting a specific child's profiles
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
        """Check if the current user is a child account managed by a parent."""
        from apps.accounts.models import ParentChild
        return ParentChild.objects.filter(child=self.request.user, is_active=True).exists()

    def create(self, request, *args, **kwargs):
        # Managed children can only create their very first (primary) profile
        # during onboarding. Additional profiles must be created by the parent.
        if self._is_managed_child():
            already_has_profile = PlayerProfile.objects.filter(user=request.user).exists()
            if already_has_profile:
                return Response(
                    {'detail': 'Contas de filho não podem criar perfis esportivos adicionais. Peça ao responsável para gerenciar seus perfis.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
        # Enforce dependent profile limit for parent accounts
        if request.user.role == 'parent':
            from apps.billing.models import Subscription
            current_count = PlayerProfile.objects.filter(user=request.user).count()
            try:
                sub = request.user.subscription
                max_dependent_profiles = sub.plan.max_members - 1
            except Subscription.DoesNotExist:
                max_dependent_profiles = 3  # safe default (tester plan: max_members=4 → 3 dependents)
            if current_count >= max_dependent_profiles:
                return Response(
                    {'detail': f'Limite de {max_dependent_profiles} perfil(is) de dependentes atingido para o seu plano.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        profile = serializer.save()
        from apps.registrations.tasks import match_new_profile_to_entries
        match_new_profile_to_entries.delay(profile.pk)

    def destroy(self, request, *args, **kwargs):
        # Managed children cannot delete profiles
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
        """
        Return cached Tênis Integrado results & rankings for a player profile.
        Triggers a background sync if the cache is stale (> 2 h old).
        Pass ?refresh=1 to force an inline re-sync (throttled to 30 min).
        """
        profile = self.get_object()

        from .parsers import extract_ti_id, TenisScrapeError
        ti_id, source = extract_ti_id(profile.external_ids or {})

        if not ti_id:
            return Response({
                'has_ti_id': False,
                'detail': 'Nenhum ID do Tênis Integrado vinculado a este perfil.',
                'results': [],
                'rankings': [],
            })

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

        # Inline sync when: forced, cache timestamps missing, or cache is empty
        # (empty cache catches old broken syncs that returned no data)
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
                    'results_synced_at': profile.ti_results_synced_at,
                    'rankings_synced_at': profile.ti_rankings_synced_at,
                }, status=status.HTTP_429_TOO_MANY_REQUESTS)

            _sync_ti_data_inline(profile, ti_id)
        elif results_stale or rankings_stale:
            # Background sync — don't block the response
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
            'results_synced_at': profile.ti_results_synced_at,
            'rankings_synced_at': profile.ti_rankings_synced_at,
        })

    @action(detail=True, methods=['post'], url_path='ti-sync')
    def ti_sync(self, request, pk=None):
        """Force an immediate re-sync of TI data. Throttled to once per 30 min."""
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
