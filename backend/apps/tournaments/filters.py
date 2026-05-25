import math

from django.db.models import Q
from django_filters import rest_framework as filters
from .models import TournamentEdition


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two (lat, lon) points."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class TournamentEditionFilter(filters.FilterSet):
    from_date = filters.DateFilter(field_name='start_date', lookup_expr='gte')
    to_date = filters.DateFilter(field_name='start_date', lookup_expr='lte')
    state = filters.CharFilter(field_name='venue__state', lookup_expr='iexact')
    city = filters.CharFilter(field_name='venue__city', lookup_expr='icontains')
    organization = filters.NumberFilter(field_name='tournament__organization_id')
    organization_slug = filters.CharFilter(method='filter_org_slug')
    modality = filters.CharFilter(field_name='tournament__modality', lookup_expr='iexact')
    circuit = filters.CharFilter(field_name='tournament__circuit', lookup_expr='icontains')
    surface = filters.CharFilter(field_name='surface')
    status = filters.CharFilter(field_name='status')
    q = filters.CharFilter(method='filter_search')
    near_profile = filters.NumberFilter(method='filter_near_profile')

    # Category filters (RF-009/RF-010): match by raw source text, normalized FK,
    # or normalized category code (e.g. "GA", "16M", "Gold M1").
    category = filters.CharFilter(method='filter_category')
    category_id = filters.NumberFilter(field_name='categories__normalized_category_id')
    category_code = filters.CharFilter(
        field_name='categories__normalized_category__code', lookup_expr='iexact'
    )

    class Meta:
        model = TournamentEdition
        fields = [
            'from_date', 'to_date', 'state', 'city', 'organization',
            'organization_slug', 'modality', 'circuit', 'surface',
            'status', 'q', 'near_profile',
            'category', 'category_id', 'category_code',
        ]

    @property
    def qs(self):
        # Always apply distinct() because category filters traverse a 1-to-N relation
        # and would otherwise duplicate editions with multiple matching categories.
        return super().qs.distinct()

    def filter_category(self, queryset, name, value):
        """Match by raw source text OR normalized category code."""
        if not value:
            return queryset
        return queryset.filter(
            Q(categories__source_category_text__icontains=value)
            | Q(categories__normalized_category__code__iexact=value)
            | Q(categories__normalized_category__label_ptbr__icontains=value)
        )

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(title__icontains=value)
            | Q(tournament__canonical_name__icontains=value)
            | Q(tournament__circuit__icontains=value)
            | Q(tournament__organization__name__icontains=value)
            | Q(tournament__organization__short_name__icontains=value)
            | Q(source_name__icontains=value)
            | Q(venue__name__icontains=value)
            | Q(venue__city__icontains=value)
        )

    def filter_org_slug(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(tournament__organization__short_name__iexact=value)

    def filter_near_profile(self, queryset, name, value):
        """Filter editions whose venue is within the profile's travel_radius_km."""
        from apps.players.models import PlayerProfile
        try:
            profile = PlayerProfile.objects.get(
                pk=value, user=self.request.user
            )
        except PlayerProfile.DoesNotExist:
            return queryset

        if not profile.home_lat or not profile.home_lng:
            # Cannot compute distance without valid coordinates - return nothing
            # rather than silently using 0,0 (Gulf of Guinea) as origin.
            return queryset.none()

        radius_km = profile.travel_radius_km or 100
        # Pre-filter: only editions with geocoded venues
        candidates = queryset.filter(
            venue__latitude__isnull=False,
            venue__longitude__isnull=False,
        ).select_related('venue')

        matching_ids = [
            ed.id for ed in candidates
            if _haversine_km(
                profile.home_lat, profile.home_lng,
                ed.venue.latitude, ed.venue.longitude,
            ) <= radius_km
        ]
        return queryset.filter(id__in=matching_ids)
