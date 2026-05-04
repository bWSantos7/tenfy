from django.contrib import admin
from .models import IngestionRun, IngestionArtifact


@admin.register(IngestionRun)
class IngestionRunAdmin(admin.ModelAdmin):
    list_display = ('data_source', 'status', 'started_at', 'finished_at',
                    'items_fetched', 'items_created', 'items_updated', 'changes_detected')
    list_filter = ('status', 'data_source', 'triggered_by')
    readonly_fields = ('started_at', 'finished_at', 'metrics', 'error_summary',
                       'items_fetched', 'items_created', 'items_updated',
                       'changes_detected', 'data_source', 'triggered_by')


@admin.register(IngestionArtifact)
class IngestionArtifactAdmin(admin.ModelAdmin):
    list_display = ('artifact_type', 'source_url', 'run', 'fetched_at', 'size_bytes')
    list_filter = ('artifact_type',)
    readonly_fields = ('created_at', 'updated_at', 'fetched_at', 'checksum')
