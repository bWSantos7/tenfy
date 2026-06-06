from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from apps.core.models import TimestampedModel


class PlayerCategory(TimestampedModel):
    """
    Taxonomy reference for categories: age buckets, classes (1..5), seniors ranges etc.
    Used by the eligibility engine as a canonical taxonomy.
    """
    TAXONOMY_FPT_CLASS = 'fpt_class'
    TAXONOMY_FPT_AGE = 'fpt_age'
    TAXONOMY_CBT_AGE = 'cbt_age'
    TAXONOMY_SENIORS = 'seniors'
    TAXONOMY_KIDS = 'kids'
    TAXONOMY_OPEN = 'open'

    TAXONOMY_CHOICES = [
        (TAXONOMY_FPT_CLASS, 'FPT - Classe'),
        (TAXONOMY_FPT_AGE, 'FPT - Idade'),
        (TAXONOMY_CBT_AGE, 'CBT - Idade'),
        (TAXONOMY_SENIORS, 'Seniors'),
        (TAXONOMY_KIDS, 'Kids'),
        (TAXONOMY_OPEN, 'Open/Profissional'),
    ]

    GENDER_M = 'M'
    GENDER_F = 'F'
    GENDER_MIXED = 'X'
    GENDER_ANY = '*'
    GENDER_CHOICES = [
        (GENDER_M, 'Masculino'),
        (GENDER_F, 'Feminino'),
        (GENDER_MIXED, 'Mistas'),
        (GENDER_ANY, 'Qualquer'),
    ]

    taxonomy = models.CharField(max_length=30, choices=TAXONOMY_CHOICES)
    code = models.CharField(max_length=50, help_text='e.g. 4M1, 14M, 35+')
    label_ptbr = models.CharField(max_length=120)
    gender_scope = models.CharField(max_length=2, choices=GENDER_CHOICES, default=GENDER_ANY)
    min_age = models.PositiveIntegerField(null=True, blank=True)
    max_age = models.PositiveIntegerField(null=True, blank=True)
    class_level = models.PositiveIntegerField(null=True, blank=True, help_text='1..5 for FPT classes')
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['taxonomy', 'code']
        constraints = [
            models.UniqueConstraint(fields=['taxonomy', 'code', 'gender_scope'], name='unique_taxonomy_code_gender'),
        ]
        indexes = [
            models.Index(fields=['taxonomy']),
            models.Index(fields=['code']),
        ]

    def __str__(self):
        return f'[{self.taxonomy}] {self.code} - {self.label_ptbr}'


class PlayerProfile(TimestampedModel):
    """
    A competitive profile that belongs to a user.
    A single user may manage multiple profiles (coach / parent mode).
    """
    # Níveis padronizados conforme CBT (Task 12): faixa etária, não habilidade.
    # ≤10 → Crianças, 11-18 → Juvenil, 19-59 → Profissional, ≥60 → Idosos.
    LEVEL_KIDS = 'kids'
    LEVEL_YOUTH = 'youth'
    LEVEL_PRO = 'pro'
    LEVEL_SENIORS = 'seniors'
    LEVEL_CHOICES = [
        (LEVEL_KIDS, 'Crianças'),
        (LEVEL_YOUTH, 'Juvenil'),
        (LEVEL_PRO, 'Profissional'),
        (LEVEL_SENIORS, 'Idosos'),
    ]

    GENDER_M = 'M'
    GENDER_F = 'F'
    GENDER_CHOICES = [
        (GENDER_M, 'Masculino'),
        (GENDER_F, 'Feminino'),
    ]

    HAND_RIGHT = 'R'
    HAND_LEFT = 'L'
    HAND_CHOICES = [(HAND_RIGHT, 'Destro'), (HAND_LEFT, 'Canhoto')]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='player_profiles'
    )
    display_name = models.CharField(max_length=120)
    birth_year = models.PositiveIntegerField(null=True, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True)
    home_state = models.CharField(max_length=2, blank=True)
    home_city = models.CharField(max_length=120, blank=True)
    travel_radius_km = models.PositiveIntegerField(default=100)
    competitive_level = models.CharField(
        max_length=20, choices=LEVEL_CHOICES, default=LEVEL_PRO
    )
    dominant_hand = models.CharField(max_length=1, choices=HAND_CHOICES, blank=True)
    is_primary = models.BooleanField(default=True)
    external_ids = models.JSONField(default=dict, blank=True, help_text='CBT id, ITF id, etc')
    home_lat = models.FloatField(null=True, blank=True)
    home_lng = models.FloatField(null=True, blank=True)
    federation = models.ForeignKey(
        'sources.Organization',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='player_profiles',
        limit_choices_to={'type': 'federation'},
        help_text='Single federation the player competes for. Its UF (state) drives '
                  'eligibility/location filtering. Replaces the legacy travel_states.',
    )
    travel_states = ArrayField(
        models.CharField(max_length=2),
        blank=True,
        default=list,
        help_text='Legacy/fallback: UFs where the player accepts travelling to compete '
                  '(e.g. ["SP","RJ","MG"]). Superseded by `federation`. Empty = not set.',
    )
    preferred_modality = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text='Preferred tournament modality: tennis, beach_tennis, padel, wheelchair. Empty = not set.',
    )

    # ── Tênis Integrado cache ────────────────────────────────────────────────────
    # Scraped data is cached here to avoid hammering the external site.
    # Refreshed on-demand (max once per 30 min) or via Celery task.
    ti_results_cache = models.JSONField(default=list, blank=True)
    ti_rankings_cache = models.JSONField(default=list, blank=True)
    ti_results_synced_at = models.DateTimeField(null=True, blank=True)
    ti_rankings_synced_at = models.DateTimeField(null=True, blank=True)
    ti_sync_error = models.CharField(max_length=300, blank=True)

    # ── UTR (Universal Tennis Rating) ────────────────────────────────────────────
    # User confirms their UTR profile via in-app search; ratings cached here.
    utr_player_id = models.CharField(max_length=50, blank=True, help_text='Confirmed UTR profile ID')
    utr_display_name = models.CharField(max_length=200, blank=True)
    utr_singles = models.CharField(max_length=20, blank=True, help_text='e.g. 4.35 or 4.xx')
    utr_doubles = models.CharField(max_length=20, blank=True)
    utr_profile_url = models.CharField(max_length=300, blank=True)
    utr_synced_at = models.DateTimeField(null=True, blank=True)
    utr_sync_error = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ['-is_primary', '-created_at']
        constraints = [
            models.UniqueConstraint(fields=['user', 'display_name'], name='unique_user_display_name'),
        ]
        indexes = [
            models.Index(fields=['user', 'is_primary']),
            models.Index(fields=['home_state']),
            models.Index(fields=['competitive_level']),
        ]

    def __str__(self):
        return f'{self.display_name} ({self.user.email})'

    @property
    def sporting_age(self):
        if not self.birth_year:
            return None
        from django.utils import timezone
        return timezone.now().year - self.birth_year

    @property
    def federation_state(self) -> str:
        """UF of the player's federation, uppercased. Empty when not set.

        This is the canonical state used by the eligibility/location engine.
        Keyed by UF (not acronym) to avoid ambiguity between federations that
        share a short_name (e.g. FCT — Carioca/RJ vs Catarinense/SC).
        """
        if self.federation_id and self.federation and self.federation.state:
            return self.federation.state.upper()
        return ''


class ExternalPlayerRanking(TimestampedModel):
    """
    Local catalogue of athletes imported from public Tênis Integrado ranking lists.

    One row = one athlete's standing in a specific (ranking, category, season).
    Unlike registrations.FederationEntry (which is tied to a tournament edition),
    these rows are pure ranking data and double as a name→TI-profile-id index used
    to auto-link Tenfy PlayerProfiles.

    Never invent data: every row preserves its source_url and raw_data so the
    origin stays traceable, and `confidence` reflects that it came from an
    official public page.
    """

    SOURCE_CBT = 'cbt'
    SOURCE_FPT = 'fpt'
    SOURCE_FCT = 'fct'
    SOURCE_FBT = 'fbt'
    SOURCE_FED = 'fed'
    SOURCE_CHOICES = [
        (SOURCE_CBT, 'CBT — Confederação Brasileira de Tênis'),
        (SOURCE_FPT, 'FPT — Federação Paulista de Tênis'),
        (SOURCE_FCT, 'FCT — Federação Catarinense de Tênis'),
        (SOURCE_FBT, 'FBT — Federação Baiana de Tênis'),
        (SOURCE_FED, 'Federação (via Tênis Integrado)'),
    ]

    CONFIDENCE_HIGH = 'high'
    CONFIDENCE_MEDIUM = 'medium'
    CONFIDENCE_LOW = 'low'
    CONFIDENCE_CHOICES = [
        (CONFIDENCE_HIGH, 'Alta — página oficial pública'),
        (CONFIDENCE_MEDIUM, 'Média'),
        (CONFIDENCE_LOW, 'Baixa'),
    ]

    # ── Athlete identity ─────────────────────────────────────────────────────
    ti_player_id = models.CharField(
        max_length=20, db_index=True,
        help_text='Numeric Tênis Integrado profile id (perfil2/index/{id})',
    )
    player_name = models.CharField(max_length=200)
    player_name_normalized = models.CharField(
        max_length=200, blank=True, db_index=True,
        help_text='Accent/case-folded name used for auto-linking lookups',
    )
    uf = models.CharField(max_length=2, blank=True)
    age = models.PositiveIntegerField(null=True, blank=True)
    club = models.CharField(max_length=200, blank=True)

    # ── Ranking context ──────────────────────────────────────────────────────
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, db_index=True)
    federation = models.CharField(max_length=120, blank=True)
    ranking_external_id = models.CharField(
        max_length=20, db_index=True,
        help_text='TI ranking id (ranking_painel_classif/index/{id})',
    )
    ranking_name = models.CharField(max_length=200, blank=True)
    category_code = models.CharField(
        max_length=20, blank=True, help_text='TI id_categoria value',
    )
    category_label = models.CharField(max_length=200, blank=True)
    modality = models.CharField(max_length=40, blank=True, default='')

    # ── Ranking values ───────────────────────────────────────────────────────
    position = models.PositiveIntegerField(null=True, blank=True)
    points = models.CharField(max_length=20, blank=True)
    wtn = models.CharField(max_length=20, blank=True)
    season = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    classified_at = models.DateField(
        null=True, blank=True, help_text='Cut-off (corte) date of the standing',
    )

    # ── Provenance ───────────────────────────────────────────────────────────
    source_url = models.URLField(max_length=500, blank=True)
    confidence = models.CharField(
        max_length=10, choices=CONFIDENCE_CHOICES, default=CONFIDENCE_HIGH,
    )
    raw_data = models.JSONField(default=dict, blank=True)
    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['source', 'ranking_external_id', 'category_code', 'position']
        constraints = [
            models.UniqueConstraint(
                fields=['source', 'ranking_external_id', 'category_code', 'ti_player_id', 'season'],
                name='unique_external_ranking_entry',
            ),
        ]
        indexes = [
            models.Index(fields=['player_name_normalized']),
            models.Index(fields=['ti_player_id']),
            models.Index(fields=['source', 'ranking_external_id']),
            models.Index(fields=['source', 'season']),
        ]

    def __str__(self):
        pos = f'{self.position}º ' if self.position else ''
        return f'{pos}{self.player_name} (TI {self.ti_player_id}) — {self.source}/{self.category_label}'


class PlayerProfileCategory(TimestampedModel):
    """Links a player profile to categories they play."""
    CONFIDENCE_DECLARED = 'declared'
    CONFIDENCE_VERIFIED = 'verified'
    CONFIDENCE_CHOICES = [
        (CONFIDENCE_DECLARED, 'Auto-declarado'),
        (CONFIDENCE_VERIFIED, 'Verificado'),
    ]

    profile = models.ForeignKey(
        PlayerProfile, on_delete=models.CASCADE, related_name='profile_categories'
    )
    category = models.ForeignKey(
        PlayerCategory, on_delete=models.CASCADE, related_name='profile_categories'
    )
    is_primary = models.BooleanField(default=False)
    confidence = models.CharField(
        max_length=20, choices=CONFIDENCE_CHOICES, default=CONFIDENCE_DECLARED
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['profile', 'category'], name='unique_profile_category'),
        ]

    def __str__(self):
        return f'{self.profile.display_name} <> {self.category.code}'
