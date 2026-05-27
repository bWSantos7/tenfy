from rest_framework import serializers
from .models import WatchlistItem, TournamentResult
from apps.tournaments.serializers import TournamentEditionListSerializer


class TournamentResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = TournamentResult
        fields = ('id', 'category_played', 'position', 'wins', 'losses', 'notes', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')


class WatchlistItemSerializer(serializers.ModelSerializer):
    edition_detail = TournamentEditionListSerializer(source='edition', read_only=True)
    result = TournamentResultSerializer(read_only=True)
    is_registered = serializers.SerializerMethodField()

    class Meta:
        model = WatchlistItem
        fields = (
            'id', 'edition', 'edition_detail', 'profile', 'user_status', 'notes',
            'alert_on_deadline', 'alert_on_changes', 'alert_on_draws',
            'result', 'is_registered', 'created_at', 'updated_at',
        )
        read_only_fields = ('created_at', 'updated_at')

    def get_is_registered(self, obj) -> bool:
        """True when a non-withdrawn TournamentRegistration exists for this user+edition."""
        from apps.registrations.models import TournamentRegistration
        from apps.players.models import PlayerProfile
        profile_ids = list(
            PlayerProfile.objects
            .filter(user_id=obj.user_id)
            .values_list('id', flat=True)
        )
        if not profile_ids:
            return False
        return TournamentRegistration.objects.filter(
            profile_id__in=profile_ids,
            edition_id=obj.edition_id,
            is_withdrawn=False,
        ).exists()

    def create(self, validated_data):
        user = self.context['request'].user
        obj, created = WatchlistItem.objects.update_or_create(
            user=user,
            edition=validated_data['edition'],
            defaults={k: v for k, v in validated_data.items() if k != 'edition'},
        )
        return obj
