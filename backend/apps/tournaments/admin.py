from django.contrib import admin
from .models import (
    Tournament, TournamentEdition, TournamentCategory,
    TournamentLink, TournamentChangeEvent, Venue,
)


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'state')
    list_filter = ('state',)
    search_fields = ('name', 'city')


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = ('canonical_name', 'organization', 'circuit', 'modality')
    list_filter = ('organization', 'circuit', 'modality')
    search_fields = ('canonical_name', 'canonical_slug')
    prepopulated_fields = {'canonical_slug': ('canonical_name',)}


class TournamentCategoryInline(admin.TabularInline):
    model = TournamentCategory
    extra = 0
    autocomplete_fields = ('normalized_category',)


class TournamentLinkInline(admin.TabularInline):
    model = TournamentLink
    extra = 0


@admin.register(TournamentEdition)
class TournamentEditionAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'season_year', 'status', 'start_date', 'entry_close_at',
        'data_confidence', 'is_manual_override',
    )
    list_filter = ('status', 'season_year', 'surface', 'data_confidence', 'is_manual_override')
    search_fields = ('title', 'tournament__canonical_name')
    readonly_fields = ('fetched_at', 'raw_content_hash', 'created_at', 'updated_at')
    inlines = [TournamentCategoryInline, TournamentLinkInline]


@admin.register(TournamentCategory)
class TournamentCategoryAdmin(admin.ModelAdmin):
    list_display = ('source_category_text', 'edition', 'normalized_category', 'price_brl')
    search_fields = ('source_category_text',)


@admin.register(TournamentChangeEvent)
class TournamentChangeEventAdmin(admin.ModelAdmin):
    list_display = ('edition', 'event_type', 'detected_at')
    list_filter = ('event_type',)
    readonly_fields = ('edition', 'event_type', 'field_changes', 'detected_at', 'ingestion_run')
