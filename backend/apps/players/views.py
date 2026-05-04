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
        return (
            PlayerProfile.objects
            .filter(user=self.request.user)
            .prefetch_related('profile_categories__category')
            .order_by('-is_primary', '-created_at')
        )

    def destroy(self, request, *args, **kwargs):
        profile = self.get_object()
        if request.user.role == 'player':
            return Response(
                {'detail': 'Contas do tipo jogador devem manter o proprio perfil esportivo.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def set_primary(self, request, pk=None):
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
