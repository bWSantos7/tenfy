from rest_framework import viewsets, permissions
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from rest_framework import serializers as rf_serializers

from .models import RuleSet, RuleVersion, RuleClause
from .services import EligibilityEngine
from apps.players.models import PlayerProfile
from apps.tournaments.models import TournamentEdition
from apps.core.permissions import IsAdminOrReadOnly
from apps.core.throttles import HeavyUserThrottle


class RuleSetSerializer(rf_serializers.ModelSerializer):
    organization_name = rf_serializers.CharField(source='organization.name', read_only=True)

    class Meta:
        model = RuleSet
        fields = ('id', 'organization', 'organization_name', 'name', 'scope', 'description')


class RuleVersionSerializer(rf_serializers.ModelSerializer):
    class Meta:
        model = RuleVersion
        fields = (
            'id', 'ruleset', 'version', 'effective_from', 'effective_to',
            'source_url', 'fetched_at', 'status', 'notes',
        )


class RuleClauseSerializer(rf_serializers.ModelSerializer):
    class Meta:
        model = RuleClause
        fields = ('id', 'rule_version', 'clause_type', 'category_code', 'logic', 'human_text')


class RuleSetViewSet(viewsets.ModelViewSet):
    queryset = RuleSet.objects.select_related('organization').all()
    serializer_class = RuleSetSerializer
    permission_classes = [IsAdminOrReadOnly]
    filterset_fields = ('organization', 'scope')


class RuleVersionViewSet(viewsets.ModelViewSet):
    queryset = RuleVersion.objects.select_related('ruleset').all()
    serializer_class = RuleVersionSerializer
    permission_classes = [IsAdminOrReadOnly]
    filterset_fields = ('ruleset', 'status')


class RuleClauseViewSet(viewsets.ModelViewSet):
    queryset = RuleClause.objects.all()
    serializer_class = RuleClauseSerializer
    permission_classes = [IsAdminOrReadOnly]
    filterset_fields = ('rule_version', 'clause_type')


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
@throttle_classes([HeavyUserThrottle])
def evaluate_edition(request, edition_id):
    """GET /api/eligibility/evaluate/?profile_id=X&edition_id=Y"""
    profile_id = request.query_params.get('profile_id')
    if not profile_id:
        # try primary profile
        profile = PlayerProfile.objects.filter(
            user=request.user, is_primary=True
        ).first()
        if not profile:
            return Response({'error': 'profile_id é obrigatório'}, status=400)
    else:
        profile = get_object_or_404(PlayerProfile, pk=profile_id, user=request.user)

    edition = get_object_or_404(
        TournamentEdition.objects.prefetch_related('categories__normalized_category'),
        pk=edition_id,
    )
    engine = EligibilityEngine(profile)
    return Response(engine.evaluate_edition(edition))
