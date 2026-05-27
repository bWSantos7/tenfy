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


class PlayerCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PlayerCategory.objects.all()
    serializer_class = PlayerCategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ('taxonomy', 'gender_scope', 'class_level')
    search_fields = ('code', 'label_ptbr')
