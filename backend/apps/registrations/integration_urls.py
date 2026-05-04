from django.urls import path
from .integration_views import federation_sync_targets, parse_entries

urlpatterns = [
    path('federation-sync-targets/', federation_sync_targets, name='federation-sync-targets'),
    path('parse-entries/', parse_entries, name='parse-entries'),
]
