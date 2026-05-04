from rest_framework import viewsets, serializers as rf_serializers, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.core.permissions import IsAdmin
from .models import IngestionRun, IngestionArtifact
from .tasks import run_source, run_all_active_sources


class IngestionRunSerializer(rf_serializers.ModelSerializer):
    source_name = rf_serializers.CharField(source='data_source.source_name', read_only=True)

    class Meta:
        model = IngestionRun
        fields = (
            'id', 'data_source', 'source_name', 'started_at', 'finished_at',
            'status', 'items_fetched', 'items_created', 'items_updated',
            'changes_detected', 'error_summary', 'metrics', 'triggered_by',
        )


class IngestionArtifactSerializer(rf_serializers.ModelSerializer):
    class Meta:
        model = IngestionArtifact
        fields = (
            'id', 'run', 'artifact_type', 'source_url', 'storage_path',
            'content_excerpt', 'checksum', 'fetched_at', 'size_bytes',
        )


class IngestionRunViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = IngestionRun.objects.select_related('data_source').all()
    serializer_class = IngestionRunSerializer
    permission_classes = [IsAdmin]
    filterset_fields = ('data_source', 'status', 'triggered_by')

    @action(detail=False, methods=['post'], url_path='run-all')
    def trigger_all(self, request):
        result = run_all_active_sources.delay()
        return Response({'task_id': result.id, 'detail': 'Dispatched all sources'})


class IngestionArtifactViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = IngestionArtifact.objects.all()
    serializer_class = IngestionArtifactSerializer
    permission_classes = [IsAdmin]
    filterset_fields = ('artifact_type', 'run')
