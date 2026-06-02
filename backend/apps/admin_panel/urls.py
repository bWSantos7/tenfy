from django.urls import path
from .views import (
    dashboard, review_queue, stats,
    user_list, user_detail, user_set_password,
    edition_patch, edition_create, admin_editions_list,
    data_sources_list, data_source_patch, connector_status,
    ingestion_runs_list, execution_logs,
    trigger_itf_sync, trigger_cosat_sync,
)

urlpatterns = [
    path('dashboard/', dashboard, name='admin-dashboard'),
    path('review-queue/', review_queue, name='admin-review-queue'),
    path('stats/', stats, name='admin-stats'),
    path('users/', user_list, name='admin-user-list'),
    path('users/<int:pk>/', user_detail, name='admin-user-detail'),
    path('users/<int:pk>/set-password/', user_set_password, name='admin-user-set-password'),
    path('editions/', edition_create, name='admin-edition-create'),
    path('editions-list/', admin_editions_list, name='admin-editions-list'),
    path('editions/<int:pk>/', edition_patch, name='admin-edition-patch'),
    path('sources/', data_sources_list, name='admin-sources-list'),
    path('sources/<int:pk>/', data_source_patch, name='admin-source-patch'),
    path('connector-status/', connector_status, name='admin-connector-status'),
    path('runs/', ingestion_runs_list, name='admin-runs-list'),
    path('execution-logs/', execution_logs, name='admin-execution-logs'),
    path('sync/itf/', trigger_itf_sync, name='admin-sync-itf'),
    path('sync/cosat/', trigger_cosat_sync, name='admin-sync-cosat'),
]
