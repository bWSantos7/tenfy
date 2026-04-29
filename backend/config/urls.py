from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)


def health_check(request):
    """Health check that validates DB connectivity for Railway load-balancer probes."""
    from django.db import connection, OperationalError
    try:
        connection.ensure_connection()
        db_ok = True
    except OperationalError:
        db_ok = False
    payload = {'status': 'ok' if db_ok else 'degraded', 'db': 'ok' if db_ok else 'error'}
    return JsonResponse(payload, status=200 if db_ok else 503)


def root_view(request):
    return JsonResponse({
        'name': 'Tournament Hub API',
        'version': '1.0.0',
        'docs': '/api/docs/',
        'health': '/health/',
    })


urlpatterns = [
    path('', root_view),
    path('health/', health_check),
    path('admin/', admin.site.urls),

    # API endpoints
    path('api/auth/', include('apps.accounts.urls')),
    path('api/players/', include('apps.players.urls')),
    path('api/tournaments/', include('apps.tournaments.urls')),
    path('api/eligibility/', include('apps.eligibility.urls')),
    path('api/watchlist/', include('apps.watchlist.urls')),
    path('api/alerts/', include('apps.alerts.urls')),
    path('api/sources/', include('apps.sources.urls')),
    path('api/ingestion/', include('apps.ingestion.urls')),
    path('api/audit/', include('apps.audit.urls')),
    path('api/admin-panel/', include('apps.admin_panel.urls')),
    path('api/marketplace/', include('apps.marketplace.urls')),
    path('api/registrations/', include('apps.registrations.urls')),
    path('api/billing/', include('apps.billing.urls')),
    path('api/integrations/', include('apps.registrations.integration_urls')),

    # API schema
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
