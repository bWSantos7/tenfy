from django.urls import path
from .views import FederationEntryViewSet, RegistrationViewSet, federation_import, trigger_matching, debug_matching

reg = RegistrationViewSet.as_view
fed = FederationEntryViewSet.as_view

urlpatterns = [
    # ── Player ───────────────────────────────────────────────────────────────
    path('', reg({'post': 'create'}), name='registration-create'),
    path('my/', reg({'get': 'my_registrations'}), name='registration-my'),
    path('<int:pk>/withdraw/', reg({'delete': 'withdraw'}), name='registration-withdraw'),

    # ── Public ────────────────────────────────────────────────────────────────
    path('edition/<int:edition_id>/public/', reg({'get': 'public_list'}), name='registration-public-list'),

    # ── Admin: registrations ─────────────────────────────────────────────────
    path('edition/<int:edition_id>/', reg({'get': 'edition_list'}), name='registration-edition-list'),
    path('<int:pk>/confirm-payment/', reg({'post': 'confirm_payment'}), name='registration-confirm-payment'),
    path('<int:pk>/reset-payment/', reg({'post': 'reset_payment'}), name='registration-reset-payment'),
    path('<int:pk>/update-ranking/', reg({'patch': 'update_ranking'}), name='registration-update-ranking'),
    path('bulk-payment/', reg({'post': 'bulk_payment'}), name='registration-bulk-payment'),

    # ── Federation entries ────────────────────────────────────────────────────
    path('federation/', fed({'post': 'create'}), name='fedentry-create'),
    path('federation/<int:pk>/', fed({'patch': 'partial_update', 'delete': 'destroy'}), name='fedentry-detail'),
    path('federation/bulk-import/', fed({'post': 'bulk_import'}), name='fedentry-bulk-import'),
    path('federation/clear/<int:edition_id>/', fed({'delete': 'clear_edition'}), name='fedentry-clear'),

    # ── External import — n8n / pipelines (AllowAny + token check inside) ────
    path('import/', federation_import, name='federation-import'),

    # ── Zero-click matching trigger (called by n8n after bulk-import) ─────────
    path('match/<int:edition_id>/', trigger_matching, name='federation-trigger-matching'),
    path('debug-matching/<int:edition_id>/', debug_matching, name='federation-debug-matching'),
]
