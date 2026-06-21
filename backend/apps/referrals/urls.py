"""Rotas da área exclusiva do parceiro (/api/partner/)."""
from django.urls import path

from .partner_views import (
    partner_me, partner_dashboard, partner_coupons, partner_usages,
)

urlpatterns = [
    path('me/', partner_me, name='partner-me'),
    path('dashboard/', partner_dashboard, name='partner-dashboard'),
    path('coupons/', partner_coupons, name='partner-coupons'),
    path('usages/', partner_usages, name='partner-usages'),
]
