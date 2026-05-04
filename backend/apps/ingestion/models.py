from django.db import models
from apps.core.models import TimestampedModel
from apps.sources.models import DataSource


class IngestionRun(TimestampedModel):
    STATUS_RUNNING = 'running'
    STATUS_SUCCESS = 'success'
    STATUS_PARTIAL = 'partial'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_RUNNING, 'Em execução'),
        (STATUS_SUCCESS, 'Sucesso'),
        (STATUS_PARTIAL, 'Parcial'),
        (STATUS_FAILED, 'Falha'),
    ]

    data_source = models.ForeignKey(
        DataSource, on_delete=models.CASCADE, related_name='runs'
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=STATUS_RUNNING)
    items_fetched = models.PositiveIntegerField(default=0)
    items_created = models.PositiveIntegerField(default=0)
    items_updated = models.PositiveIntegerField(default=0)
    changes_detected = models.PositiveIntegerField(default=0)
    error_summary = models.TextField(blank=True)
    metrics = models.JSONField(default=dict, blank=True)
    triggered_by = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['data_source', '-started_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f'Run #{self.pk} src={self.data_source_id} {self.status}'


class IngestionArtifact(TimestampedModel):
    ARTIFACT_HTML = 'html'
    ARTIFACT_PDF = 'pdf'
    ARTIFACT_JSON = 'json'
    ARTIFACT_TEXT = 'text'
    ARTIFACT_CHOICES = [
        (ARTIFACT_HTML, 'HTML'),
        (ARTIFACT_PDF, 'PDF'),
        (ARTIFACT_JSON, 'JSON'),
        (ARTIFACT_TEXT, 'Texto'),
    ]

    run = models.ForeignKey(
        IngestionRun, on_delete=models.CASCADE, related_name='artifacts'
    )
    artifact_type = models.CharField(max_length=10, choices=ARTIFACT_CHOICES)
    source_url = models.URLField(max_length=500)
    storage_path = models.CharField(max_length=500, blank=True)
    content_excerpt = models.TextField(blank=True)
    checksum = models.CharField(max_length=64, blank=True, db_index=True)
    fetched_at = models.DateTimeField(auto_now_add=True)
    size_bytes = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-fetched_at']
        indexes = [
            models.Index(fields=['checksum']),
        ]

    def __str__(self):
        return f'{self.artifact_type} @ {self.source_url[:60]}'
