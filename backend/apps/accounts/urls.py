from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    RegisterView,
    register_start,
    register_verify_email,
    register_resend_email,
    register_complete,
    register_status,
    CustomTokenObtainPairView,
    MeView,
    change_password,
    logout,
    delete_account,
    upload_avatar,
    send_email_otp,
    verify_email_otp,
    password_reset_request,
    password_reset_confirm,
    data_export,
    CoachAthleteViewSet,
    ParentChildViewSet,
    DependentInviteViewSet,
)

class ThrottledTokenRefreshView(TokenRefreshView):
    """Wraps simplejwt's TokenRefreshView with a scoped rate limit (20/hour)."""
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'token_refresh'


router = DefaultRouter()
router.register('coach/athletes', CoachAthleteViewSet, basename='coach-athlete')
router.register('children', ParentChildViewSet, basename='parent-child')
router.register('invites', DependentInviteViewSet, basename='dependent-invite')

urlpatterns = [
    path('', include(router.urls)),
    path('register/', RegisterView.as_view(), name='register'),
    # Cadastro diferido (conta só criada na 1ª entrada)
    path('register/start/', register_start, name='register_start'),
    path('register/verify-email/', register_verify_email, name='register_verify_email'),
    path('register/resend-email/', register_resend_email, name='register_resend_email'),
    path('register/complete/', register_complete, name='register_complete'),
    path('register/status/', register_status, name='register_status'),
    path('login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', ThrottledTokenRefreshView.as_view(), name='token_refresh'),
    path('logout/', logout, name='logout'),
    path('me/', MeView.as_view(), name='me'),
    path('me/avatar/', upload_avatar, name='upload_avatar'),
    path('change-password/', change_password, name='change_password'),
    path('delete-account/', delete_account, name='delete_account'),
    # OTP verification
    path('send-email-otp/', send_email_otp, name='send_email_otp'),
    path('verify-email/', verify_email_otp, name='verify_email_otp'),
    # Password reset
    path('password-reset/', password_reset_request, name='password_reset_request'),
    path('password-reset/confirm/', password_reset_confirm, name='password_reset_confirm'),
    # LGPD data export
    path('data-export/', data_export, name='data_export'),
]
