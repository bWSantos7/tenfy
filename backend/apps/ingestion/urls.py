from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import IngestionRunViewSet, IngestionArtifactViewSet
from .webhook_views import import_tournaments_webhook

router = DefaultRouter()
router.register('runs', IngestionRunViewSet, basename='ingestion-run')
router.register('artifacts', IngestionArtifactViewSet, basename='ingestion-artifact')

urlpatterns = router.urls + [
    path('webhook/import-tournaments/', import_tournaments_webhook, name='ingestion-webhook-import'),
]
