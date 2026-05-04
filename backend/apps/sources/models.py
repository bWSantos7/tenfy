from django.db import models
from apps.core.models import TimestampedModel


class Organization(TimestampedModel):
    TYPE_CONFEDERATION = 'confederation'
    TYPE_FEDERATION = 'federation'
    TYPE_PLATFORM = 'platform'
    TYPE_CLUB = 'club'
    TYPE_MEDIA = 'media'
    TYPE_CHOICES = [
        (TYPE_CONFEDERATION, 'Confederação'),
        (TYPE_FEDERATION, 'Federação'),
        (TYPE_PLATFORM, 'Plataforma'),
        (TYPE_CLUB, 'Clube'),
        (TYPE_MEDIA, 'Mídia'),
    ]

    name = models.CharField(max_length=200, unique=True)
    short_name = models.CharField(max_length=20, blank=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    website_url = models.URLField(blank=True)
    logo_url = models.URLField(blank=True)
    state = models.CharField(max_length=2, blank=True, help_text='UF para federações estaduais')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['type']),
            models.Index(fields=['state']),
        ]

    def __str__(self):
        return self.short_name or self.name


class DataSource(TimestampedModel):
    SOURCE_TYPE_HTML = 'html'
    SOURCE_TYPE_PDF = 'pdf'
    SOURCE_TYPE_JSON = 'json'
    SOURCE_TYPE_MANUAL = 'manual'
    SOURCE_TYPE_CHOICES = [
        (SOURCE_TYPE_HTML, 'HTML Scraping'),
        (SOURCE_TYPE_PDF, 'PDF Parsing'),
        (SOURCE_TYPE_JSON, 'JSON API'),
        (SOURCE_TYPE_MANUAL, 'Manual'),
    ]

    PRIORITY_CHOICES = [
        ('P0', 'Crítica'),
        ('P1', 'Alta'),
        ('P2', 'Média'),
        ('P3', 'Baixa'),
    ]

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='data_sources'
    )
    source_name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPE_CHOICES)
    base_url = models.URLField()
    connector_key = models.CharField(
        max_length=100,
        help_text='Key matching a connector class (e.g. fpt_public, cbt_regulation)'
    )
    fetch_schedule_cron = models.CharField(
        max_length=100,
        default='0 * * * *',
        help_text='Cron expression for scheduler'
    )
    enabled = models.BooleanField(default=True)
    priority = models.CharField(max_length=2, choices=PRIORITY_CHOICES, default='P1')
    legal_notes = models.TextField(blank=True)
    config_json = models.JSONField(default=dict, blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_run_status = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ['organization__name', 'source_name']
        indexes = [
            models.Index(fields=['enabled']),
            models.Index(fields=['connector_key']),
        ]

    def __str__(self):
        return f'{self.organization.short_name or self.organization.name} - {self.source_name}'
