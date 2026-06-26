from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import AlertViewSet, preferences, push_subscribe, register_device

router = DefaultRouter()
router.register('', AlertViewSet, basename='alert')

urlpatterns = [
    path('preferences/', preferences, name='alert-preferences'),
    path('push-subscribe/', push_subscribe, name='push-subscribe'),
    path('register-device/', register_device, name='register-device'),
] + router.urls
