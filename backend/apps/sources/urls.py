from rest_framework.routers import DefaultRouter
from .views import OrganizationViewSet, DataSourceViewSet

router = DefaultRouter()
router.register('organizations', OrganizationViewSet)
router.register('data-sources', DataSourceViewSet)

urlpatterns = router.urls
