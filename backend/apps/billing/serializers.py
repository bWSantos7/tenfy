from decimal import Decimal
from rest_framework import serializers
from .models import FamilyMembership, Feature, Payment, Plan, PlanFeature, Subscription, WebhookEvent


class FeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feature
        fields = ('id', 'name', 'code', 'description')


class PlanFeatureSerializer(serializers.ModelSerializer):
    code  = serializers.CharField(source='feature.code', read_only=True)
    name  = serializers.CharField(source='feature.name', read_only=True)

    class Meta:
        model = PlanFeature
        fields = ('code', 'name', 'limit')


class PlanSerializer(serializers.ModelSerializer):
    features     = PlanFeatureSerializer(source='plan_features', many=True, read_only=True)
    is_available = serializers.SerializerMethodField()

    def get_is_available(self, obj):
        return obj.slug == Plan.SLUG_TESTER

    class Meta:
        model = Plan
        fields = (
            'id', 'name', 'slug', 'price_monthly', 'price_yearly',
            'description', 'highlight_label', 'display_order', 'is_active',
            'max_members', 'features', 'is_available',
        )


class SubscriptionSerializer(serializers.ModelSerializer):
    plan_name    = serializers.CharField(source='plan.name', read_only=True)
    plan_slug    = serializers.CharField(source='plan.slug', read_only=True)
    price_monthly = serializers.DecimalField(source='plan.price_monthly', max_digits=8, decimal_places=2, read_only=True)
    price_yearly  = serializers.DecimalField(source='plan.price_yearly',  max_digits=8, decimal_places=2, read_only=True)

    class Meta:
        model = Subscription
        fields = (
            'id', 'plan', 'plan_name', 'plan_slug',
            'billing_period', 'status', 'is_active',
            'pending_plan', 'pending_billing_period',
            'start_date', 'next_due_date',
            'cancel_at_period_end', 'canceled_at',
            'asaas_subscription_id',
            'price_monthly', 'price_yearly',
            'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'status', 'pending_plan', 'pending_billing_period', 'start_date', 'next_due_date',
            'asaas_subscription_id', 'canceled_at',
            'created_at', 'updated_at',
        )


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = (
            'id', 'amount', 'payment_method', 'status',
            'transaction_id', 'due_date', 'paid_at',
            'description', 'pix_code', 'boleto_url', 'created_at',
        )
        read_only_fields = fields


class CheckoutSerializer(serializers.Serializer):
    plan_slug      = serializers.ChoiceField(choices=['individual', 'familia', 'tester'])
    billing_period = serializers.ChoiceField(choices=['monthly', 'yearly'], default='monthly')
    payment_method = serializers.ChoiceField(
        choices=['credit_card', 'pix', 'debit_card', 'boleto'], default='pix'
    )
    # PCI-DSS: backend only accepts a tokenized card reference, NEVER raw card data.
    # Client-side tokenization is performed directly with Asaas from the mobile device.
    card_token = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, attrs):
        if attrs.get('payment_method') == 'credit_card' and not attrs.get('card_token', '').strip():
            raise serializers.ValidationError(
                {'card_token': 'card_token é obrigatório para pagamento com cartão de crédito.'}
            )
        return attrs


class FamilyMembershipSerializer(serializers.ModelSerializer):
    member_email = serializers.EmailField(source='member_user.email', read_only=True)
    member_name  = serializers.CharField(source='member_user.full_name', read_only=True)

    class Meta:
        model = FamilyMembership
        fields = ('id', 'member_email', 'member_name', 'status', 'accepted_at', 'created_at')
        read_only_fields = fields


class CancelSubscriptionSerializer(serializers.Serializer):
    immediate = serializers.BooleanField(default=False, help_text='True = cancela agora; False = cancela no fim do período')


class FamilyMemberAddSerializer(serializers.Serializer):
    """Add a dependent to a Família subscription by email or user_id."""
    email   = serializers.EmailField(required=False, allow_blank=True)
    user_id = serializers.IntegerField(required=False)

    def validate(self, attrs):
        if not attrs.get('email') and not attrs.get('user_id'):
            raise serializers.ValidationError('Informe email ou user_id.')
        return attrs
