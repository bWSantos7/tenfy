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
    venue_state = filters.CharFilter(field_name='venue__state', lookup_expr='iexact')
    city = filters.CharFilter(field_name='venue__city', lookup_expr='icontains')
    organization = filters.NumberFilter(field_name='tournament__organization_id')
    organization_slug = filters.CharFilter(method='filter_org_slug')
    modality = filters.CharFilter(field_name='tournament__modality', lookup_expr='iexact')
    circuit = filters.CharFilter(field_name='tournament__circuit', lookup_expr='icontains')
    surface = filters.CharFilter(field_name='surface')
    # Status filter operates on the *dynamic* status (computed from dates), so it
    # matches the badge shown on the card — not the stored `status` field, which
    # is often stale (e.g. stored 'open' but already finished by end_date).
    status = filters.CharFilter(method='filter_status')
    # Exclusão por status dinâmico (vírgula). A agenda usa para ocultar status terminais
    # (lista: closed,finished,canceled; calendário: finished,canceled) sem enumerar os
    # ativos — assim qualquer torneio não-terminal/futuro continua aparecendo.
    status_exclude = filters.CharFilter(method='filter_status_exclude')
    q = filters.CharFilter(method='filter_search')
    near_profile = filters.NumberFilter(method='filter_near_profile')
    # Country filter (RF Task 7) — value is an ISO alpha-3 code (BRA, ARG, CHL...).
    country = filters.CharFilter(method='filter_country')

    # Category filters (RF-009/RF-010): match by raw source text, normalized FK,
    # or normalized category code (e.g. "GA", "16M", "Gold M1").
    category = filters.CharFilter(method='filter_category')
    category_id = filters.NumberFilter(field_name='categories__normalized_category_id')
    category_code = filters.CharFilter(
        field_name='categories__normalized_category__code', lookup_expr='iexact'
    )
    # Filtro por idade exata da categoria (o "número" da categoria, ex.: "BS 14" ->
    # 14), independente de gênero/rótulo — casa com PlayerCategory.max_age das
    # taxonomias etárias (cbt_age/kids), que já guarda esse número seedado.
    # Alimenta o combo de categorias da aba Torneios (ver action `category_ages`).
    category_age = filters.NumberFilter(field_name='categories__normalized_category__max_age')

    # Level-based tournament type filter derived from PlayerProfile.competitive_level.
    # Automatically applied by the frontend/mobile based on the active profile.
    # Values (níveis CBT): 'kids' | 'youth' | 'pro' | 'seniors'
    player_level = filters.CharFilter(method='filter_player_level')

    # Filtro explícito de categoria etária (distinto de `player_level`, que é amplo
    # e implícito por perfil). Usado pelo filtro Kids/Infantojuvenil da aba Torneios
    # para o responsável sem nenhum perfil vinculado escolher manualmente o que ver.
    # Aceita um ou mais valores separados por vírgula (ex.: 'kids,youth'), igual ao
    # filtro de status — kids, youth, os dois, ou nenhum (sem esse recorte).
    age_category = filters.CharFilter(method='filter_age_category')

    class Meta:
        model = TournamentEdition
        fields = [
            'from_date', 'to_date', 'state', 'venue_state', 'city', 'organization',
            'organization_slug', 'modality', 'circuit', 'surface',
            'status', 'status_exclude', 'q', 'near_profile', 'country',
            'category', 'category_id', 'category_code', 'category_age',
            'player_level', 'age_category',
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

    def filter_country(self, queryset, name, value):
        """Filter by tournament country. Accepts one or more comma-separated
        country codes (the frontend sends every code variant for a country,
        e.g. 'CHI,CHL', because ITF uses IOC codes while COSAT uses ISO).

        Brazil is special: international sources tag venues with 'BRA', but the
        Brazilian federations (CBT/FPT/FCT) leave country_code empty. So 'BRA'
        also matches the empty code.
        """
        if not value:
            return queryset
        codes = [c.strip().upper() for c in value.split(',') if c.strip()]
        if not codes:
            return queryset
        q = Q()
        brazil = {'BRA', 'BR', 'BRASIL'}
        if any(c in brazil for c in codes):
            q |= Q(venue__country_code__iexact='BRA') | Q(venue__country_code='')
        others = [c for c in codes if c not in brazil]
        if others:
            q |= Q(venue__country_code__in=others)
        return queryset.filter(q)

    def filter_status(self, queryset, name, value):
        """Filter by dynamic status (the value shown on the card). Aceita um ou mais
        status separados por vírgula (ex.: ``open,closing_soon``) — combinados por OR.
        Mapeia cada status para as mesmas condições por data de
        TournamentEdition.compute_dynamic_status(). Valores desconhecidos são ignorados."""
        raw = (value or '').strip().lower()
        if not raw:
            return queryset
        statuses = [s.strip() for s in raw.split(',') if s.strip()]
        combined = None
        for status in statuses:
            q = TournamentEdition.dynamic_status_q(status)
            if q is None:
                continue  # ignora termos desconhecidos sem zerar os demais
            combined = q if combined is None else (combined | q)
        if combined is None:
            # Nenhum status reconhecido → sem correspondência (evita devolver tudo).
            return queryset.none()
        return queryset.filter(combined)

    def filter_status_exclude(self, queryset, name, value):
        """Exclui editions cujo status DINÂMICO esteja na lista (vírgula). Ao contrário de
        um include-list, mostra qualquer status que NÃO seja terminal — então anunciados e
        próximos não somem por casarem mal com a definição estrita de cada status."""
        raw = (value or '').strip().lower()
        if not raw:
            return queryset
        combined = None
        for status in [s.strip() for s in raw.split(',') if s.strip()]:
            q = TournamentEdition.dynamic_status_q(status)
            if q is None:
                continue
            combined = q if combined is None else (combined | q)
        if combined is None:
            return queryset
        return queryset.exclude(combined)

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        # unaccent__icontains: accent-insensitive + case-insensitive search
        # (requires the unaccent PostgreSQL extension, installed via migration 0009)
        return queryset.filter(
            Q(title__unaccent__icontains=value)
            | Q(tournament__canonical_name__unaccent__icontains=value)
            | Q(tournament__circuit__unaccent__icontains=value)
            | Q(tournament__organization__name__unaccent__icontains=value)
            | Q(tournament__organization__short_name__unaccent__icontains=value)
            | Q(source_name__unaccent__icontains=value)
            | Q(venue__name__unaccent__icontains=value)
            | Q(venue__city__unaccent__icontains=value)
        )

    def filter_org_slug(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(tournament__organization__short_name__iexact=value)

    def filter_player_level(self, queryset, name, value):
        """
        Coarse tournament-type filter based on PlayerProfile.competitive_level
        (níveis CBT — Task 12):

        'kids'    → is_kids=True (torneios com categoria Kids) OU is_youth=True/None
                    (mantém a visibilidade ampla que já existia para infantojuvenil).
        'youth'   → is_youth=True/None. Um torneio misto (Kids + Juvenil no mesmo
                    evento) continua visível — só exclui o que é EXCLUSIVAMENTE Kids
                    (is_kids=True e is_youth não-True).
        'pro'/'seniors' (adultos)
                  → is_youth=False/None, e SEMPRE exclui is_kids=True (mesmo torneios
                    mistos não fazem sentido pra um perfil adulto).

        ``circuit__icontains`` fica como rede de segurança adicional: dados vindos
        do tournament-extractor sempre gravam circuit='Infantojuvenil' (não reflete
        o conteúdo real), então esse texto nunca casa com 'kids'/'juvenil' pra essas
        fontes — quem carrega esse peso hoje é o campo booleano is_kids/is_youth.
        """
        if not value:
            return queryset

        if value == 'kids':
            return queryset.filter(
                Q(is_kids=True) | Q(is_youth=True) | Q(is_youth__isnull=True)
            )

        if value == 'youth':
            return (
                queryset
                .filter(Q(is_youth=True) | Q(is_youth__isnull=True))
                .exclude(tournament__circuit__icontains='kids')
                .exclude(Q(is_kids=True) & ~Q(is_youth=True))
            )

        if value in ('pro', 'seniors'):
            return (
                queryset
                .filter(Q(is_youth=False) | Q(is_youth__isnull=True))
                .exclude(
                    Q(tournament__circuit__icontains='juvenil') |
                    Q(tournament__circuit__icontains='kids') |
                    Q(is_kids=True)
                )
            )

        return queryset

    def filter_age_category(self, queryset, name, value):
        """
        Seleção manual de categoria etária (diferente de `player_level`, que é amplo
        por design pra cobrir a visibilidade de um perfil real). Usado pelo filtro
        Kids/Infantojuvenil (caixinhas, igual ao filtro de Status) oferecido ao
        responsável sem nenhum perfil vinculado, que quer escolher manualmente o que
        ver na aba Torneios. Aceita um ou mais valores separados por vírgula:

        'kids'  → torneios com categoria Kids (is_kids=True). Um torneio misto
                  (Kids + Juvenil) tem categoria Kids de verdade, então continua
                  aparecendo aqui também.
        'youth' → torneios Infantojuvenil (is_youth=True ou ainda não classificado),
                  excluindo o que é EXCLUSIVAMENTE Kids.
        'kids,youth' (os dois marcados) → união das duas regras acima.
        """
        raw = (value or '').strip().lower()
        if not raw:
            return queryset
        selected = {c.strip() for c in raw.split(',') if c.strip()}
        combined = None
        if 'kids' in selected:
            combined = Q(is_kids=True)
        if 'youth' in selected:
            youth_q = (Q(is_youth=True) | Q(is_youth__isnull=True)) & ~(Q(is_kids=True) & ~Q(is_youth=True))
            combined = youth_q if combined is None else (combined | youth_q)
        if combined is None:
            return queryset
        return queryset.filter(combined)

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
