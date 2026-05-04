from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import AlertViewSet, preferences, push_subscribe

router = DefaultRouter()
router.register('', AlertViewSet, basename='alert')

urlpatterns = [
    path('preferences/', preferences, name='alert-preferences'),
    path('push-subscribe/', push_subscribe, name='push-subscribe'),
] + router.urls
