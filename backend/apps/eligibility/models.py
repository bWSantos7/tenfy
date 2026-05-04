from django.db import models
from apps.core.models import TimestampedModel
from apps.sources.models import Organization





class RuleSet(TimestampedModel):
    """A named set of rules e.g. 'FPT Abertos', 'CBT Infantojuvenil'."""
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='rulesets'
    )
    name = models.CharField(max_length=200)
    scope = models.CharField(
        max_length=50,
        help_text='e.g. fpt_abertos, cbt_juvenil, fpt_seniors, cbt_kids'
    )
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['organization__name', 'name']
        unique_together = ('organization', 'scope')

    def __str__(self):
        return f'{self.organization.short_name} - {self.name}'


class RuleVersion(TimestampedModel):
    STATUS_DRAFT = 'draft'
    STATUS_ACTIVE = 'active'
    STATUS_DEPRECATED = 'deprecated'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Rascunho'),
        (STATUS_ACTIVE, 'Ativa'),
        (STATUS_DEPRECATED, 'Depreciada'),
    ]

    ruleset = models.ForeignKey(RuleSet, on_delete=models.CASCADE, related_name='versions')
    version = models.CharField(max_length=20, help_text='e.g. 2026.1')
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    source_url = models.URLField(max_length=500, blank=True)
    fetched_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-effective_from']
        unique_together = ('ruleset', 'version')

    def __str__(self):
        return f'{self.ruleset.name} v{self.version}'


class RuleClause(TimestampedModel):
    TYPE_AGE = 'age'
    TYPE_CLASS = 'class'
    TYPE_MEMBERSHIP = 'membership'
    TYPE_RANKING = 'ranking'
    TYPE_GENDER = 'gender'
    TYPE_GENERIC = 'generic'
    TYPE_CHOICES = [
        (TYPE_AGE, 'Idade'),
        (TYPE_CLASS, 'Classe'),
        (TYPE_MEMBERSHIP, 'Filiação'),
        (TYPE_RANKING, 'Ranking'),
        (TYPE_GENDER, 'Gênero'),
        (TYPE_GENERIC, 'Genérica'),
    ]

    rule_version = models.ForeignKey(
        RuleVersion, on_delete=models.CASCADE, related_name='clauses'
    )
    clause_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    category_code = models.CharField(max_length=50, blank=True,
                                     help_text='Category this clause applies to, blank = all')
    logic = models.JSONField(
        default=dict,
        help_text='Machine-readable logic, e.g. {"min_age":14,"max_age":14,"gender":"M"}'
    )
    human_text = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['rule_version', 'category_code']),
            models.Index(fields=['clause_type']),
        ]

    def __str__(self):
        return f'{self.rule_version} :: {self.clause_type} :: {self.category_code}'


class TournamentRuleBinding(TimestampedModel):
    """
    Binds a specific TournamentEdition to a RuleSet (and optionally a pinned RuleVersion).

    When a tournament has a binding, the eligibility engine uses that specific ruleset
    instead of the global active ruleset for the organization.
    This allows CBT and FPT tournaments to have different rule versions simultaneously.
    """
    edition = models.ForeignKey(
        'tournaments.TournamentEdition',
        on_delete=models.CASCADE,
        related_name='rule_bindings',
    )
    ruleset = models.ForeignKey(
        RuleSet,
        on_delete=models.PROTECT,
        related_name='tournament_bindings',
    )
    # If set, pins a specific version. If null, the engine resolves the active version at runtime.
    pinned_version = models.ForeignKey(
        RuleVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pinned_bindings',
        help_text='Leave blank to always use the active version of the ruleset',
    )
    binding_reason = models.CharField(
        max_length=200,
        blank=True,
        help_text='e.g. "2026 season rules", "CBT infantojuvenil reg 2026"',
    )
    is_primary = models.BooleanField(
        default=True,
        help_text='Primary binding used for eligibility evaluation',
    )

    class Meta:
        ordering = ['-is_primary', '-created_at']
        indexes = [
            models.Index(fields=['edition', 'is_primary']),
        ]
        unique_together = ('edition', 'ruleset')

    def __str__(self):
        version = f' @ {self.pinned_version}' if self.pinned_version else ' (active)'
        return f'{self.edition} → {self.ruleset}{version}'

    def resolve_version(self) -> 'RuleVersion | None':
        """Return the pinned version, or the current active version of the ruleset."""
        if self.pinned_version:
            return self.pinned_version
        return (
            self.ruleset.versions
            .filter(status=RuleVersion.STATUS_ACTIVE)
            .order_by('-effective_from')
            .first()
        )
