"""Serializers do programa de parceiros (uso no painel admin — Fase 4)."""
from rest_framework import serializers

from .models import CommissionLedger, CommissionRule, Coupon, Partner, Payout


class PartnerSerializer(serializers.ModelSerializer):
    coupons_count = serializers.IntegerField(source='coupons.count', read_only=True)
    login_email = serializers.SerializerMethodField()
    has_login = serializers.SerializerMethodField()

    class Meta:
        model = Partner
        fields = (
            'id', 'name', 'type', 'email', 'phone', 'status',
            'payout_method', 'payout_details', 'notes',
            'coupons_count', 'login_email', 'has_login',
            'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'coupons_count', 'login_email', 'has_login', 'created_at', 'updated_at')

    def get_login_email(self, obj):
        return obj.user.email if obj.user_id else None

    def get_has_login(self, obj):
        return bool(obj.user_id and obj.user.is_active)


class CouponSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source='partner.name', read_only=True)

    class Meta:
        model = Coupon
        fields = (
            'id', 'code', 'partner', 'partner_name',
            'discount_type', 'discount_value', 'plan_scope',
            'starts_at', 'expires_at',
            'max_total_uses', 'max_uses_per_customer', 'times_used',
            'status', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'partner_name', 'times_used', 'created_at', 'updated_at')


class CommissionRuleSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source='partner.name', read_only=True)
    coupon_code = serializers.CharField(source='coupon.code', read_only=True, default=None)

    class Meta:
        model = CommissionRule
        fields = (
            'id', 'partner', 'partner_name', 'coupon', 'coupon_code',
            'commission_type', 'commission_value',
            'rule_scope', 'base_amount_type', 'status',
            'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'partner_name', 'coupon_code', 'created_at', 'updated_at')


class CommissionLedgerSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source='partner.name', read_only=True)
    coupon_code = serializers.CharField(source='coupon.code', read_only=True, default=None)
    customer_email = serializers.SerializerMethodField()

    class Meta:
        model = CommissionLedger
        fields = (
            'id', 'partner', 'partner_name', 'coupon', 'coupon_code',
            'subscription', 'payment', 'commission_rule', 'payout',
            'customer_email', 'base_amount', 'commission_amount', 'status',
            'created_at', 'updated_at',
        )
        read_only_fields = fields

    def get_customer_email(self, obj):
        if obj.subscription_id and obj.subscription and obj.subscription.user_id:
            return obj.subscription.user.email
        return None


class PayoutSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source='partner.name', read_only=True)
    commissions_count = serializers.IntegerField(source='commissions.count', read_only=True)

    class Meta:
        model = Payout
        fields = (
            'id', 'partner', 'partner_name', 'amount', 'status',
            'method', 'reference', 'notes', 'paid_at',
            'commissions_count', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'partner_name', 'commissions_count', 'created_at', 'updated_at')
