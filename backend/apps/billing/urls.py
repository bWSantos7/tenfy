from django.urls import path
from . import views

urlpatterns = [
    path('plans/',                       views.plans_list,               name='billing_plans_list'),
    path('subscription/',                views.subscription_detail,      name='billing_subscription_detail'),
    path('subscription/checkout/',       views.subscription_checkout,    name='billing_subscription_checkout'),
    path('checkout/validate-coupon/',    views.checkout_validate_coupon, name='billing_checkout_validate_coupon'),
    path('checkout/session/',            views.checkout_session,         name='billing_checkout_session'),
    path('subscription/cancel/',         views.subscription_cancel,      name='billing_subscription_cancel'),
    path('subscription/reactivate/',     views.subscription_reactivate,  name='billing_subscription_reactivate'),
    path('payments/',                    views.payment_history,          name='billing_payment_history'),
    path('features/',                    views.my_features,              name='billing_my_features'),
    path('webhooks/asaas/',              views.asaas_webhook,            name='billing_asaas_webhook'),
    path('webhooks/asaas/status/',       views.asaas_webhook_status,     name='billing_asaas_webhook_status'),
    path('asaas-customer-id/',           views.asaas_customer_id,        name='billing_asaas_customer_id'),
    path('family/members/',              views.family_members,           name='billing_family_members'),
    path('family/members/<int:pk>/',     views.family_member_detail,     name='billing_family_member_detail'),
]
