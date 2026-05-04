from rest_framework.routers import DefaultRouter
from .views import PlayerProfileViewSet, PlayerCategoryViewSet

router = DefaultRouter()
router.register('profiles', PlayerProfileViewSet, basename='player-profile')
router.register('categories', PlayerCategoryViewSet, basename='player-category')

urlpatterns = router.urls
