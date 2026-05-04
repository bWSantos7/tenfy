from rest_framework.routers import DefaultRouter
from .views import IngestionRunViewSet, IngestionArtifactViewSet

router = DefaultRouter()
router.register('runs', IngestionRunViewSet, basename='ingestion-run')
router.register('artifacts', IngestionArtifactViewSet, basename='ingestion-artifact')
urlpatterns = router.urls
