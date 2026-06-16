from django.contrib import admin

from .models import Coupon, CommissionLedger, CommissionRule, Partner, Payout


class CouponInline(admin.TabularInline):
    model = Coupon
    extra = 0
    fields = ('code', 'discount_type', 'discount_value', 'plan_scope', 'status')


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display  = ('name', 'type', 'status', 'email', 'phone', 'payout_method', 'created_at')
    list_filter   = ('status', 'type')
    search_fields = ('name', 'email', 'phone')
    inlines = [CouponInline]


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display  = ('code', 'partner', 'discount_type', 'discount_value', 'plan_scope', 'status', 'times_used', 'max_total_uses')
    list_filter   = ('status', 'discount_type', 'plan_scope')
    search_fields = ('code', 'partner__name')
    autocomplete_fields = ('partner',)


@admin.register(CommissionRule)
class CommissionRuleAdmin(admin.ModelAdmin):
    list_display  = ('partner', 'coupon', 'commission_type', 'commission_value', 'rule_scope', 'base_amount_type', 'status')
    list_filter   = ('status', 'commission_type', 'rule_scope', 'base_amount_type')
    search_fields = ('partner__name', 'coupon__code')
    autocomplete_fields = ('partner', 'coupon')


@admin.register(CommissionLedger)
class CommissionLedgerAdmin(admin.ModelAdmin):
    list_display  = ('partner', 'commission_amount', 'base_amount', 'status', 'subscription', 'payment', 'payout', 'created_at')
    list_filter   = ('status',)
    search_fields = ('partner__name', 'coupon__code')
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ('partner', 'coupon', 'commission_rule', 'payout')


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display  = ('partner', 'amount', 'status', 'method', 'reference', 'paid_at', 'created_at')
    list_filter   = ('status',)
    search_fields = ('partner__name', 'reference')
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ('partner',)
