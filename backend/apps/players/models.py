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
    LEVEL_AMATEUR = 'amateur'
    LEVEL_FEDERATED = 'federated'
    LEVEL_YOUTH = 'youth'
    LEVEL_PRO = 'pro'
    LEVEL_BEGINNER = 'beginner'
    LEVEL_CHOICES = [
        (LEVEL_BEGINNER, 'Principiante'),
        (LEVEL_AMATEUR, 'Amador'),
        (LEVEL_FEDERATED, 'Federado'),
        (LEVEL_YOUTH, 'Juvenil'),
        (LEVEL_PRO, 'Profissional'),
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
        max_length=20, choices=LEVEL_CHOICES, default=LEVEL_AMATEUR
    )
    dominant_hand = models.CharField(max_length=1, choices=HAND_CHOICES, blank=True)
    tennis_class = models.CharField(
        max_length=10, blank=True,
        help_text='FPT class: 1,2,3,4,5,PR,PRO'
    )
    is_primary = models.BooleanField(default=True)
    external_ids = models.JSONField(default=dict, blank=True, help_text='CBT id, ITF id, etc')
    home_lat = models.FloatField(null=True, blank=True)
    home_lng = models.FloatField(null=True, blank=True)
    travel_states = ArrayField(
        models.CharField(max_length=2),
        blank=True,
        default=list,
        help_text='UFs where the player accepts travelling to compete (e.g. ["SP","RJ","MG"]). Empty = not set.',
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
