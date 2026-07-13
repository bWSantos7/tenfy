from django.db import models
from django.utils import timezone
from apps.core.models import TimestampedModel
from apps.sources.models import Organization, DataSource


class Venue(TimestampedModel):
    name = models.CharField(max_length=200)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=2, blank=True)
    country = models.CharField(max_length=120, blank=True)
    country_code = models.CharField(max_length=3, blank=True, help_text='ISO 3166-1 alpha-3 (e.g. BRA, FRA)')
    address = models.CharField(max_length=300, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['state']),
            models.Index(fields=['city']),
        ]
        unique_together = ('name', 'city', 'state')

    def __str__(self):
        return f'{self.name} ({self.city}/{self.state})' if self.city else self.name


class Tournament(TimestampedModel):
    """Logical tournament identity (stable across years)."""
    canonical_name = models.CharField(max_length=300)
    canonical_slug = models.SlugField(max_length=300, unique=True)
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name='tournaments'
    )
    circuit = models.CharField(max_length=100, blank=True,
                               help_text='e.g. Abertos, Interclubes, Infantojuvenil, Kids, Seniors')
    modality = models.CharField(max_length=50, default='tennis',
                                help_text='tennis, beach_tennis, padel, wheelchair')
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['canonical_name']
        indexes = [
            models.Index(fields=['organization']),
            models.Index(fields=['modality']),
            models.Index(fields=['circuit']),
        ]

    def __str__(self):
        return self.canonical_name


class TournamentEdition(TimestampedModel):
    STATUS_UNKNOWN = 'unknown'
    STATUS_ANNOUNCED = 'announced'
    STATUS_OPEN = 'open'
    STATUS_CLOSING_SOON = 'closing_soon'
    STATUS_CLOSED = 'closed'
    STATUS_DRAWS_PUBLISHED = 'draws_published'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_FINISHED = 'finished'
    STATUS_CANCELED = 'canceled'
    STATUS_CHOICES = [
        (STATUS_UNKNOWN, 'Desconhecido'),
        (STATUS_ANNOUNCED, 'Anunciado'),
        (STATUS_OPEN, 'Inscrições Abertas'),
        (STATUS_CLOSING_SOON, 'Encerrando em breve'),
        (STATUS_CLOSED, 'Inscrições Encerradas'),
        (STATUS_DRAWS_PUBLISHED, 'Chaves Publicadas'),
        (STATUS_IN_PROGRESS, 'Em Andamento'),
        (STATUS_FINISHED, 'Finalizado'),
        (STATUS_CANCELED, 'Cancelado'),
    ]

    SURFACE_CLAY = 'clay'
    SURFACE_HARD = 'hard'
    SURFACE_GRASS = 'grass'
    SURFACE_SAND = 'sand'
    SURFACE_CARPET = 'carpet'
    SURFACE_UNKNOWN = 'unknown'
    SURFACE_CHOICES = [
        (SURFACE_CLAY, 'Saibro'),
        (SURFACE_HARD, 'Rápida / Sintética'),
        (SURFACE_GRASS, 'Grama'),
        (SURFACE_SAND, 'Areia'),
        (SURFACE_CARPET, 'Carpete'),
        (SURFACE_UNKNOWN, 'Não informada'),
    ]

    CONFIDENCE_LOW = 'low'
    CONFIDENCE_MED = 'med'
    CONFIDENCE_HIGH = 'high'
    CONFIDENCE_CHOICES = [
        (CONFIDENCE_LOW, 'Baixa'),
        (CONFIDENCE_MED, 'Média'),
        (CONFIDENCE_HIGH, 'Alta'),
    ]

    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE, related_name='editions'
    )
    season_year = models.PositiveIntegerField(db_index=True)
    external_id = models.CharField(max_length=120, blank=True, db_index=True)

    title = models.CharField(max_length=300, help_text='Title as captured from source')

    # Dates
    start_date = models.DateField(null=True, blank=True, db_index=True)
    end_date = models.DateField(null=True, blank=True)
    entry_open_at = models.DateTimeField(null=True, blank=True)
    entry_close_at = models.DateTimeField(null=True, blank=True, db_index=True)

    status = models.CharField(
        max_length=25, choices=STATUS_CHOICES, default=STATUS_UNKNOWN, db_index=True
    )
    surface = models.CharField(max_length=15, choices=SURFACE_CHOICES, default=SURFACE_UNKNOWN)

    venue = models.ForeignKey(Venue, null=True, blank=True, on_delete=models.SET_NULL, related_name='editions')

    # Pricing (stored as strings to preserve source text; numerics when parseable)
    base_price_brl = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    price_notes = models.CharField(max_length=300, blank=True)

    # Source / provenance
    data_source = models.ForeignKey(
        DataSource, null=True, blank=True, on_delete=models.SET_NULL, related_name='editions'
    )
    official_source_url = models.URLField(max_length=500, blank=True)
    source_name = models.CharField(max_length=120, blank=True)
    fetched_at = models.DateTimeField(null=True, blank=True)
    raw_content_hash = models.CharField(max_length=64, blank=True, db_index=True)
    raw_payload = models.JSONField(default=dict, blank=True)

    # Admin / curation
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        'accounts.User', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='reviewed_editions'
    )
    is_manual_override = models.BooleanField(default=False)
    data_confidence = models.CharField(
        max_length=10, choices=CONFIDENCE_CHOICES, default=CONFIDENCE_MED
    )

    # Inscription timeline extras
    withdrawal_deadline_at = models.DateTimeField(
        null=True, blank=True,
        help_text='Deadline to withdraw from tournament after registering.',
    )
    has_online_entry = models.BooleanField(
        default=False,
        help_text='True when the source indicates online registration is available.',
    )

    # Youth classification
    is_youth = models.BooleanField(
        null=True, blank=True, db_index=True,
        help_text='True = torneio infantojuvenil (categorias até 18 anos). Null = não classificado.',
    )
    # Kids classification (categorias abaixo de 12 anos). Independente de is_youth:
    # um torneio pode ter as duas (categorias kids E juvenis no mesmo evento).
    is_kids = models.BooleanField(
        default=False, db_index=True,
        help_text='True = torneio tem categoria(s) Kids (abaixo de 12 anos).',
    )

    # Cross-source deduplication fingerprint (sha1 of title+date+city)
    dedup_fingerprint = models.CharField(
        max_length=16, blank=True, db_index=True,
        help_text='Short hash for cross-source dedup (title+date+city). Empty = not computed.',
    )

    # Publication state — admin can hide editions from public listing
    # without deleting them (preserves provenance).
    is_published = models.BooleanField(
        default=True, db_index=True,
        help_text='False = oculto da listagem pública (admin pode editar e republicar).',
    )

    # Federation sync tracking
    entries_source_url = models.URLField(
        max_length=500, blank=True,
        help_text='Melhor URL conhecida para a página de inscritos/chaves desta edição.',
    )
    candidate_entry_links = models.JSONField(
        default=list, blank=True,
        help_text='Lista de URLs candidatas para inscritos/chaves (derivadas ou extraídas).',
    )
    needs_sync = models.BooleanField(
        default=True, db_index=True,
        help_text='True quando os dados de inscritos precisam ser sincronizados.',
    )
    last_synced_at = models.DateTimeField(
        null=True, blank=True,
        help_text='Última vez que os inscritos foram sincronizados com a fonte externa.',
    )

    # Acceptance list structured data (from ITF/federation source)
    acceptance_list = models.JSONField(
        default=list, blank=True,
        help_text=(
            'Lista de inscritos por seção: '
            '[{"section": "main_draw", "players": [{"name", "country", "country_code", "ranking", "wtn", "priority", "information"}]}]'
        ),
    )
    sync_priority = models.PositiveSmallIntegerField(
        default=5,
        help_text='Prioridade de sincronização (0=menor, 30=urgente). Computado pelo backend.',
    )
    parser_available = models.BooleanField(
        default=False,
        help_text='True quando existe conector/parser capaz de extrair inscritos desta fonte.',
    )
    parser_limitation = models.CharField(
        max_length=300, blank=True,
        help_text='Descrição da limitação do parser para esta fonte, quando aplicável.',
    )

    # Data quality
    validation_errors = models.JSONField(
        default=list, blank=True,
        help_text='Erros de validação detectados na ingestão (email em cidade, UF inválida, etc.).',
    )

    class Meta:
        ordering = ['-start_date', '-entry_close_at']
        indexes = [
            models.Index(fields=['status', 'entry_close_at']),
            models.Index(fields=['start_date']),
            models.Index(fields=['season_year']),
            models.Index(fields=['raw_content_hash']),
            models.Index(fields=['dedup_fingerprint']),
        ]
        constraints = [
            # Only enforce uniqueness when external_id is non-empty.
            # Blank external_id is allowed to repeat (editions without source ID).
            models.UniqueConstraint(
                fields=['tournament', 'season_year', 'external_id'],
                condition=~models.Q(external_id=''),
                name='unique_edition_external_id',
            ),
        ]

    def __str__(self):
        return f'{self.title} ({self.season_year})'

    def compute_dynamic_status(self):
        """Compute status based on dates, preserving canceled/finished when set."""
        if self.status in [self.STATUS_CANCELED, self.STATUS_FINISHED]:
            return self.status
        now = timezone.now()
        today = now.date()
        if self.end_date and today > self.end_date:
            return self.STATUS_FINISHED
        if self.start_date and today >= self.start_date:
            return self.STATUS_IN_PROGRESS
        if self.entry_close_at and now > self.entry_close_at:
            return self.STATUS_CLOSED
        if self.entry_close_at:
            days_to_close = (self.entry_close_at - now).days
            if days_to_close <= 3:
                return self.STATUS_CLOSING_SOON
            return self.STATUS_OPEN
        if self.entry_open_at and now >= self.entry_open_at:
            return self.STATUS_OPEN
        return self.STATUS_ANNOUNCED

    @classmethod
    def dynamic_status_q(cls, value, now=None):
        """Q() selecting editions whose *dynamic* status equals `value`.

        Mirrors compute_dynamic_status() exactly so the listing/calendar status
        filter matches the badge the user sees (which is the dynamic status, not
        the stored `status` field). Returns None for unknown values.

        `canceled`/`finished` keep their stored value; all other dynamic states
        are derived from the dates, evaluated in the same short-circuit order as
        compute_dynamic_status(). `draws_published`/`unknown` are never produced
        dynamically, so they fall back to the stored `status` field.
        """
        from datetime import timedelta

        now = now or timezone.now()
        today = now.date()
        # days_to_close <= 3  ⟺  (entry_close_at - now) < 4 days  ⟺  entry_close_at < now+4d
        four_days = now + timedelta(days=4)

        # Stored terminal states win (step 1 of compute_dynamic_status).
        not_terminal = ~models.Q(status__in=[cls.STATUS_CANCELED, cls.STATUS_FINISHED])

        ended = models.Q(end_date__isnull=False, end_date__lt=today)
        not_ended = models.Q(end_date__isnull=True) | models.Q(end_date__gte=today)
        started = models.Q(start_date__isnull=False, start_date__lte=today)
        not_started = models.Q(start_date__isnull=True) | models.Q(start_date__gt=today)
        close_passed = models.Q(entry_close_at__isnull=False, entry_close_at__lt=now)
        closing_window = models.Q(
            entry_close_at__isnull=False, entry_close_at__gte=now, entry_close_at__lt=four_days
        )
        open_via_close = models.Q(entry_close_at__isnull=False, entry_close_at__gte=four_days)
        open_via_open_at = models.Q(
            entry_close_at__isnull=True, entry_open_at__isnull=False, entry_open_at__lte=now
        )
        announced_rest = models.Q(entry_close_at__isnull=True) & (
            models.Q(entry_open_at__isnull=True) | models.Q(entry_open_at__gt=now)
        )

        # Each date branch assumes the earlier branches did not match.
        if value == cls.STATUS_CANCELED:
            return models.Q(status=cls.STATUS_CANCELED)
        if value == cls.STATUS_FINISHED:
            return models.Q(status=cls.STATUS_FINISHED) | (not_terminal & ended)
        if value == cls.STATUS_IN_PROGRESS:
            return not_terminal & not_ended & started
        if value == cls.STATUS_CLOSED:
            return not_terminal & not_ended & not_started & close_passed
        if value == cls.STATUS_CLOSING_SOON:
            return not_terminal & not_ended & not_started & closing_window
        if value == cls.STATUS_OPEN:
            return not_terminal & not_ended & not_started & (open_via_close | open_via_open_at)
        if value == cls.STATUS_ANNOUNCED:
            return not_terminal & not_ended & not_started & announced_rest
        if value in (cls.STATUS_DRAWS_PUBLISHED, cls.STATUS_UNKNOWN):
            # Not producible dynamically — fall back to the stored status field.
            return models.Q(status=value)
        return None


class TournamentCategory(TimestampedModel):
    edition = models.ForeignKey(
        TournamentEdition, on_delete=models.CASCADE, related_name='categories'
    )
    source_category_text = models.CharField(max_length=200)
    normalized_category = models.ForeignKey(
        'players.PlayerCategory', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='tournament_categories'
    )
    price_brl = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    max_participants = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='Limite de vagas nesta categoria. Null = sem limite definido.'
    )
    visibility_order = models.PositiveIntegerField(default=0)
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ['visibility_order', 'source_category_text']
        indexes = [
            models.Index(fields=['edition']),
            models.Index(fields=['normalized_category']),
        ]

    def __str__(self):
        return f'{self.edition.title} :: {self.source_category_text}'


class TournamentLink(TimestampedModel):
    TYPE_REGISTRATION = 'registration'
    TYPE_REGULATION = 'regulation'
    TYPE_RESULTS = 'results'
    TYPE_DRAWS = 'draws'
    TYPE_OTHER = 'other'
    TYPE_CHOICES = [
        (TYPE_REGISTRATION, 'Inscrição'),
        (TYPE_REGULATION, 'Regulamento'),
        (TYPE_RESULTS, 'Resultados'),
        (TYPE_DRAWS, 'Chaves'),
        (TYPE_OTHER, 'Outro'),
    ]

    edition = models.ForeignKey(
        TournamentEdition, on_delete=models.CASCADE, related_name='links'
    )
    link_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    url = models.URLField(max_length=500)
    label = models.CharField(max_length=200, blank=True)
    is_official = models.BooleanField(default=True)
    source_name = models.CharField(max_length=120, blank=True)
    fetched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['link_type']
        unique_together = ('edition', 'link_type', 'url')

    def __str__(self):
        return f'{self.edition.title} - {self.link_type}'


class TournamentChangeEvent(TimestampedModel):
    EVENT_CREATED = 'created'
    EVENT_STATUS = 'status_changed'
    EVENT_DATE = 'dates_changed'
    EVENT_DEADLINE = 'deadline_changed'
    EVENT_PRICE = 'price_changed'
    EVENT_VENUE = 'venue_changed'
    EVENT_CATEGORIES = 'categories_changed'
    EVENT_CANCELED = 'canceled'
    EVENT_DRAWS = 'draws_published'
    EVENT_OTHER = 'other'
    EVENT_CHOICES = [
        (EVENT_CREATED, 'Criado'),
        (EVENT_STATUS, 'Status alterado'),
        (EVENT_DATE, 'Datas alteradas'),
        (EVENT_DEADLINE, 'Prazo alterado'),
        (EVENT_PRICE, 'Valor alterado'),
        (EVENT_VENUE, 'Local alterado'),
        (EVENT_CATEGORIES, 'Categorias alteradas'),
        (EVENT_CANCELED, 'Cancelado'),
        (EVENT_DRAWS, 'Chaves publicadas'),
        (EVENT_OTHER, 'Outro'),
    ]

    edition = models.ForeignKey(
        TournamentEdition, on_delete=models.CASCADE, related_name='change_events'
    )
    event_type = models.CharField(max_length=30, choices=EVENT_CHOICES)
    field_changes = models.JSONField(default=dict, blank=True)
    detected_at = models.DateTimeField(auto_now_add=True, db_index=True)
    ingestion_run = models.ForeignKey(
        'ingestion.IngestionRun', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='change_events'
    )

    class Meta:
        ordering = ['-detected_at']
        indexes = [
            models.Index(fields=['edition', '-detected_at']),
            models.Index(fields=['event_type']),
        ]

    def __str__(self):
        return f'{self.edition.title} - {self.event_type} @ {self.detected_at}'
