"""
Marketplace app — pós-MVP.

Provides Merchant / Offer / OfferTargeting models for a future in-app
marketplace of tennis products and services. Models and migrations exist
to preserve schema history. Endpoints are registered under /api/marketplace/
but are protected by IsAdminOrReadOnly and not exposed in mobile/frontend UI.

This module must not be removed from INSTALLED_APPS while its migration
0001_initial is referenced by the migration graph.
"""
from django.apps import AppConfig


class MarketplaceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.marketplace'
