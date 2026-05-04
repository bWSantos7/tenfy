from rest_framework.routers import DefaultRouter
from .views import (
    TournamentViewSet,
    TournamentEditionViewSet,
    TournamentEditionAdminViewSet,
)

router = DefaultRouter()
router.register('editions', TournamentEditionViewSet, basename='edition')
router.register('admin/editions', TournamentEditionAdminViewSet, basename='edition-admin')
router.register('', TournamentViewSet, basename='tournament')

urlpatterns = router.urls
