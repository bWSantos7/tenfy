from rest_framework import serializers
from .models import (
    Tournament, TournamentEdition, TournamentCategory,
    TournamentLink, TournamentChangeEvent, Venue,
)
from apps.players.serializers import PlayerCategorySerializer
from apps.sources.serializers import OrganizationSerializer


class VenueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Venue
        fields = ('id', 'name', 'city', 'state', 'address', 'latitude', 'longitude')


class TournamentLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = TournamentLink
        fields = ('id', 'link_type', 'url', 'label', 'is_official', 'source_name', 'fetched_at')


class TournamentCategorySerializer(serializers.ModelSerializer):
    normalized_category_detail = PlayerCategorySerializer(source='normalized_category', read_only=True)

    class Meta:
        model = TournamentCategory
        fields = (
            'id', 'source_category_text',
            'normalized_category', 'normalized_category_detail',
            'price_brl', 'max_participants', 'visibility_order', 'notes',
        )


class TournamentChangeEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = TournamentChangeEvent
        fields = ('id', 'event_type', 'field_changes', 'detected_at')


class TournamentSerializer(serializers.ModelSerializer):
    organization_detail = OrganizationSerializer(source='organization', read_only=True)

    class Meta:
        model = Tournament
        fields = (
            'id', 'canonical_name', 'canonical_slug',
            'organization', 'organization_detail',
            'circuit', 'modality', 'description',
        )


class TournamentEditionListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list endpoints."""
    tournament_name = serializers.CharField(source='tournament.canonical_name', read_only=True)
    organization_name = serializers.CharField(source='tournament.organization.name', read_only=True)
    organization_short = serializers.CharField(source='tournament.organization.short_name', read_only=True)
    organization_logo_url = serializers.SerializerMethodField()
    circuit = serializers.CharField(source='tournament.circuit', read_only=True)
    modality = serializers.CharField(source='tournament.modality', read_only=True)
    venue_name = serializers.CharField(source='venue.name', read_only=True, default=None)
    venue_city = serializers.CharField(source='venue.city', read_only=True, default=None)
    venue_state = serializers.CharField(source='venue.state', read_only=True, default=None)
    dynamic_status = serializers.SerializerMethodField()
    categories_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = TournamentEdition
        fields = (
            'id', 'tournament', 'tournament_name',
            'organization_name', 'organization_short', 'organization_logo_url',
            'circuit', 'modality', 'is_youth',
            'season_year', 'title',
            'start_date', 'end_date', 'entry_open_at', 'entry_close_at',
            'withdrawal_deadline_at', 'has_online_entry',
            'status', 'dynamic_status', 'surface',
            'venue_name', 'venue_city', 'venue_state',
            'base_price_brl',
            'official_source_url', 'source_name', 'fetched_at',
            'data_confidence', 'categories_count',
            'validation_errors',
        )

    def get_dynamic_status(self, obj):
        return obj.compute_dynamic_status()

    def get_organization_logo_url(self, obj):
        try:
            return obj.tournament.organization.logo_url or None
        except Exception:
            return None


class TournamentEditionDetailSerializer(serializers.ModelSerializer):
    tournament_detail = TournamentSerializer(source='tournament', read_only=True)
    venue_detail = VenueSerializer(source='venue', read_only=True)
    categories = TournamentCategorySerializer(many=True, read_only=True)
    links = TournamentLinkSerializer(many=True, read_only=True)
    change_events = TournamentChangeEventSerializer(many=True, read_only=True)
    dynamic_status = serializers.SerializerMethodField()
    reviewed_by_email = serializers.CharField(source='reviewed_by.email', read_only=True, default=None)
    organization_logo_url = serializers.SerializerMethodField()

    class Meta:
        model = TournamentEdition
        fields = (
            'id', 'tournament', 'tournament_detail',
            'season_year', 'external_id', 'title',
            'start_date', 'end_date', 'entry_open_at', 'entry_close_at',
            'withdrawal_deadline_at', 'has_online_entry',
            'status', 'dynamic_status', 'surface',
            'venue', 'venue_detail',
            'base_price_brl', 'price_notes',
            'data_source', 'official_source_url', 'source_name', 'fetched_at',
            'raw_content_hash',
            'reviewed_at', 'reviewed_by', 'reviewed_by_email',
            'is_manual_override', 'data_confidence',
            'entries_source_url', 'candidate_entry_links',
            'needs_sync', 'last_synced_at', 'sync_priority',
            'parser_available', 'parser_limitation',
            'validation_errors',
            'organization_logo_url',
            'categories', 'links', 'change_events',
            'created_at', 'updated_at',
        )

    def get_dynamic_status(self, obj):
        return obj.compute_dynamic_status()

    def get_organization_logo_url(self, obj):
        try:
            return obj.tournament.organization.logo_url or None
        except Exception:
            return None


class TournamentEditionAdminSerializer(serializers.ModelSerializer):
    """Write serializer used by admin endpoints to override data."""
    class Meta:
        model = TournamentEdition
        fields = (
            'title', 'start_date', 'end_date',
            'entry_open_at', 'entry_close_at',
            'status', 'surface', 'venue',
            'base_price_brl', 'price_notes',
            'official_source_url', 'is_manual_override', 'data_confidence',
        )


class TournamentEditionSyncSerializer(serializers.ModelSerializer):
    """Write serializer for n8n/integration sync state updates (PATCH only)."""
    class Meta:
        model = TournamentEdition
        fields = (
            'needs_sync', 'last_synced_at',
            'entries_source_url', 'candidate_entry_links',
            'sync_priority', 'parser_available', 'parser_limitation',
        )
