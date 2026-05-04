from django.contrib import admin
from .models import FamilyMembership, Feature, Payment, Plan, PlanFeature, Subscription, WebhookEvent


class PlanFeatureInline(admin.TabularInline):
    model = PlanFeature
    extra = 0
    fields = ('feature', 'limit', 'notes')
    autocomplete_fields = ('feature',)


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display  = ('name', 'slug', 'price_monthly', 'price_yearly', 'max_members', 'display_order', 'is_active')
    list_editable = ('display_order', 'is_active')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [PlanFeatureInline]


@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    list_display  = ('code', 'name', 'description')
    search_fields = ('code', 'name')


@admin.register(PlanFeature)
class PlanFeatureAdmin(admin.ModelAdmin):
    list_display  = ('plan', 'feature', 'limit', 'notes')
    list_filter   = ('plan',)
    search_fields = ('plan__name', 'feature__code')


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display   = ('user', 'plan', 'billing_period', 'status', 'start_date', 'next_due_date', 'cancel_at_period_end')
    list_filter    = ('status', 'billing_period', 'plan')
    search_fields  = ('user__email', 'asaas_subscription_id', 'asaas_customer_id')
    readonly_fields = ('created_at', 'updated_at', 'asaas_customer_id', 'asaas_subscription_id')
    date_hierarchy  = 'start_date'

    fieldsets = (
        (None, {'fields': ('user', 'plan', 'billing_period', 'status')}),
        ('Datas', {'fields': ('start_date', 'next_due_date', 'canceled_at', 'cancel_at_period_end')}),
        ('Asaas', {'fields': ('asaas_customer_id', 'asaas_subscription_id'), 'classes': ('collapse',)}),
        ('Metadados', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display   = ('user', 'amount', 'payment_method', 'status', 'paid_at', 'created_at')
    list_filter    = ('status', 'payment_method')
    search_fields  = ('user__email', 'transaction_id', 'asaas_payment_id')
    readonly_fields = ('created_at', 'updated_at', 'raw_response', 'asaas_payment_id')
    date_hierarchy  = 'created_at'


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display  = ('event_type', 'asaas_id', 'processed', 'error', 'created_at')
    list_filter   = ('event_type', 'processed')
    search_fields = ('asaas_id', 'event_type')
    readonly_fields = ('event_type', 'asaas_id', 'payload', 'processed', 'error', 'created_at', 'updated_at')


@admin.register(FamilyMembership)
class FamilyMembershipAdmin(admin.ModelAdmin):
    list_display   = ('responsible_email', 'member_user', 'status', 'accepted_at', 'created_at')
    list_filter    = ('status',)
    search_fields  = ('subscription__user__email', 'member_user__email')
    readonly_fields = ('created_at', 'updated_at', 'accepted_at')

    def responsible_email(self, obj):
        return obj.subscription.user.email
    responsible_email.short_description = 'Responsável'
