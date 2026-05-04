from rest_framework.routers import DefaultRouter
from .views import MerchantViewSet, OfferViewSet, OfferTargetingViewSet

router = DefaultRouter()
router.register('merchants', MerchantViewSet)
router.register('offers', OfferViewSet)
router.register('targetings', OfferTargetingViewSet)
urlpatterns = router.urls
