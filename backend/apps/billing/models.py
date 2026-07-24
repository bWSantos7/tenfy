"""
Billing & Subscriptions SaaS module.

Models:
  Plan             — subscription tiers (Individual, Família)
  Feature          — individual feature flags (tournament_creation, etc.)
  PlanFeature      — M2M: which features each plan includes (with optional limit)
  Subscription     — user ↔ plan binding, tracks status and Asaas IDs
  FamilyMembership — dependents linked to a Família subscription
  Payment          — individual payment/charge records
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimestampedModel


# ── Plans ──────────────────────────────────────────────────────────────────────

class Plan(TimestampedModel):
    SLUG_INDIVIDUAL = 'individual'
    SLUG_FAMILIA    = 'familia'
    SLUG_TESTER     = 'tester'

    BILLING_MONTHLY = 'monthly'
    BILLING_YEARLY  = 'yearly'
    BILLING_CHOICES = [
        (BILLING_MONTHLY, 'Mensal'),
        (BILLING_YEARLY,  'Anual'),
    ]

    name            = models.CharField(max_length=60)
    slug            = models.SlugField(max_length=30, unique=True)
    price_monthly   = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    price_yearly    = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    description     = models.TextField(blank=True)
    highlight_label = models.CharField(max_length=40, blank=True, help_text='e.g. "Mais popular"')
    display_order   = models.PositiveSmallIntegerField(default=0)
    is_active       = models.BooleanField(default=True)
    max_members     = models.PositiveSmallIntegerField(
        default=1,
        help_text='Total de perfis permitidos (responsáveis + dependentes). Individual=1, Família=5.',
    )
    max_responsibles = models.PositiveSmallIntegerField(
        default=1,
        help_text=(
            'Quantos perfis de responsável (titular + co-responsáveis) podem compartilhar '
            'esta assinatura. Dependentes permitidos = max_members - max_responsibles.'
        ),
    )

    class Meta:
        ordering = ['display_order']

    def __str__(self):
        return self.name

    def price_for_period(self, period: str) -> 'decimal.Decimal':
        return self.price_yearly if period == self.BILLING_YEARLY else self.price_monthly


# ── Feature flags ──────────────────────────────────────────────────────────────

class Feature(TimestampedModel):
    # Canonical feature codes — referenced throughout the codebase
    CODE_TOURNAMENT_CREATION    = 'tournament_creation'
    CODE_PROFILE_HIGHLIGHT      = 'profile_highlight'
    CODE_ADVANCED_STATS         = 'advanced_stats'
    CODE_RANKING_ACCESS         = 'ranking_access'
    CODE_UNLIMITED_REGISTRATIONS = 'unlimited_registrations'
    CODE_ADVANCED_FILTERS       = 'advanced_filters'
    CODE_MATCH_PRIORITY         = 'match_priority'
    CODE_PREMIUM_TOURNAMENTS    = 'premium_tournaments'
    CODE_EXPORT_DATA            = 'export_data'
    CODE_COACH_MODULE           = 'coach_module'
    CODE_MULTI_PROFILE          = 'multi_profile'
    CODE_WATCHLIST_UNLIMITED    = 'watchlist_unlimited'

    name        = models.CharField(max_length=100)
    code        = models.CharField(max_length=60, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f'{self.name} ({self.code})'


class PlanFeature(TimestampedModel):
    """Associates a Feature with a Plan, with an optional usage limit."""
    plan    = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name='plan_features')
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name='plan_features')
    # None = unlimited; numeric = cap (e.g. max 5 registrations/month for limited plans)
    limit   = models.PositiveIntegerField(null=True, blank=True, help_text='NULL = unlimited')
    notes   = models.CharField(max_length=200, blank=True)

    class Meta:
        unique_together = ('plan', 'feature')

    def __str__(self):
        cap = f' (limit={self.limit})' if self.limit is not None else ''
        return f'{self.plan.name} → {self.feature.code}{cap}'


# ── Subscriptions ──────────────────────────────────────────────────────────────

class Subscription(TimestampedModel):
    STATUS_ACTIVE   = 'active'
    STATUS_PENDING  = 'pending'
    STATUS_CANCELED = 'canceled'
    STATUS_EXPIRED  = 'expired'
    STATUS_UNPAID   = 'unpaid'
    STATUS_TRIAL    = 'trial'
    STATUS_CHOICES  = [
        (STATUS_ACTIVE,   'Ativa'),
        (STATUS_PENDING,  'Pendente'),
        (STATUS_CANCELED, 'Cancelada'),
        (STATUS_EXPIRED,  'Expirada'),
        (STATUS_UNPAID,   'Inadimplente'),
        (STATUS_TRIAL,    'Trial'),
    ]

    user                 = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscription'
    )
    plan                 = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name='subscriptions')
    billing_period       = models.CharField(max_length=10, choices=Plan.BILLING_CHOICES, default=Plan.BILLING_MONTHLY)
    status               = models.CharField(max_length=15, choices=STATUS_CHOICES, default=STATUS_PENDING)
    start_date           = models.DateField(null=True, blank=True)
    next_due_date        = models.DateField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    canceled_at          = models.DateTimeField(null=True, blank=True)

    # Asaas integration fields — populated when API is connected
    asaas_customer_id     = models.CharField(max_length=60, blank=True)
    asaas_subscription_id = models.CharField(max_length=60, blank=True)
    asaas_checkout_id     = models.CharField(max_length=60, blank=True, db_index=True)
    pending_plan = models.ForeignKey(
        Plan, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='pending_subscriptions',
    )
    pending_billing_period = models.CharField(max_length=10, choices=Plan.BILLING_CHOICES, blank=True)

    # Programa de parceiros — RN-004: no máximo 1 parceiro comissionável por assinatura.
    # String refs evitam import circular (referrals referencia billing).
    partner = models.ForeignKey(
        'referrals.Partner', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='subscriptions',
    )
    coupon = models.ForeignKey(
        'referrals.Coupon', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='subscriptions',
    )

    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['next_due_date']),
            models.Index(fields=['asaas_subscription_id']),
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return f'{self.user.email} → {self.plan.name} [{self.status}]'

    @property
    def is_active(self) -> bool:
        return self.status in (self.STATUS_ACTIVE, self.STATUS_TRIAL)

    def has_feature(self, code: str) -> bool:
        """Check if this subscription's plan includes the feature with given code."""
        return self.plan.plan_features.filter(feature__code=code).exists()

    def feature_limit(self, code: str):
        """Return the usage limit for a feature (None = unlimited, raises if not in plan)."""
        pf = self.plan.plan_features.filter(feature__code=code).first()
        if pf is None:
            return 0  # feature not in plan → effectively 0
        return pf.limit  # None = unlimited


# ── Payments ───────────────────────────────────────────────────────────────────

class Payment(TimestampedModel):
    METHOD_CREDIT_CARD = 'credit_card'
    METHOD_PIX         = 'pix'
    METHOD_DEBIT_CARD  = 'debit_card'
    METHOD_BOLETO      = 'boleto'
    METHOD_CHOICES = [
        (METHOD_CREDIT_CARD, 'Cartão de crédito'),
        (METHOD_PIX,         'Pix'),
        (METHOD_DEBIT_CARD,  'Cartão de débito'),
        (METHOD_BOLETO,      'Boleto'),
    ]

    STATUS_PENDING   = 'pending'
    STATUS_PAID      = 'paid'
    STATUS_FAILED    = 'failed'
    STATUS_REFUNDED  = 'refunded'
    STATUS_OVERDUE   = 'overdue'
    STATUS_CHOICES = [
        (STATUS_PENDING,  'Pendente'),
        (STATUS_PAID,     'Pago'),
        (STATUS_FAILED,   'Falhou'),
        (STATUS_REFUNDED, 'Estornado'),
        (STATUS_OVERDUE,  'Vencido'),
    ]

    user             = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='payments'
    )
    subscription     = models.ForeignKey(
        Subscription, null=True, blank=True, on_delete=models.SET_NULL, related_name='payments'
    )
    amount           = models.DecimalField(max_digits=10, decimal_places=2)
    # Programa de parceiros — desconto aplicado e valor líquido efetivamente recebido (RN-006).
    # paid_net_amount NULL = ainda não informado pela fonte (Asaas); base de comissão cai p/ amount.
    discount_amount  = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_net_amount  = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    payment_method   = models.CharField(max_length=15, choices=METHOD_CHOICES, blank=True)
    status           = models.CharField(max_length=15, choices=STATUS_CHOICES, default=STATUS_PENDING)
    transaction_id   = models.CharField(max_length=120, blank=True)  # Asaas payment ID
    asaas_payment_id = models.CharField(max_length=60, blank=True)
    due_date         = models.DateField(null=True, blank=True)
    paid_at          = models.DateTimeField(null=True, blank=True)
    description      = models.CharField(max_length=200, blank=True)
    pix_code         = models.TextField(blank=True, help_text='Pix copia-e-cola')
    pix_qr_code      = models.TextField(blank=True, help_text='Base64 QR code image')
    boleto_url       = models.URLField(blank=True)
    raw_response     = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['asaas_payment_id']),
        ]

    def __str__(self):
        return f'Payment R${self.amount} [{self.status}] — {self.user.email}'


# ── Webhook log ────────────────────────────────────────────────────────────────

class WebhookEvent(TimestampedModel):
    """Stores raw Asaas webhook payloads for auditing / replay."""
    event_type  = models.CharField(max_length=80)
    asaas_id    = models.CharField(max_length=60, blank=True, db_index=True)
    payload     = models.JSONField(default=dict)
    processed   = models.BooleanField(default=False)
    error       = models.TextField(blank=True)  # TextField: no char limit for full tracebacks

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'WebhookEvent {self.event_type} ({self.asaas_id})'


# ── Família membership ─────────────────────────────────────────────────────────

class FamilyMembership(TimestampedModel):
    """
    Links a co-responsável (second parent) to a Família subscription.

    The titular/payer is Subscription.user. Each FamilyMembership represents one
    extra responsável seat under that subscription — NOT a dependent (dependents are
    tracked via apps.accounts.models.ParentChild, mirrored across all responsáveis of
    the same family). The plan's max_responsibles limits how many active memberships
    a subscription can have (titular counts as 1 of that total).
    """
    STATUS_PENDING = 'pending'
    STATUS_ACTIVE  = 'active'
    STATUS_REMOVED = 'removed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pendente'),
        (STATUS_ACTIVE,  'Ativo'),
        (STATUS_REMOVED, 'Removido'),
    ]

    subscription = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name='family_members'
    )
    member_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='family_memberships'
    )
    status      = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('subscription', 'member_user')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.subscription.user.email} → {self.member_user.email} [{self.status}]'


def get_effective_subscription(user):
    """
    Return the Subscription that governs ``user``'s plan/features.

    A user's own Subscription (if any) always takes priority. Otherwise, if the
    user is an active co-responsável (FamilyMembership) of a Família subscription,
    that subscription is inherited — this is how the second responsável gets the
    same features and shared dependent quota as the titular.
    """
    try:
        return user.subscription
    except Subscription.DoesNotExist:
        pass

    membership = (
        FamilyMembership.objects
        .filter(
            member_user=user,
            status=FamilyMembership.STATUS_ACTIVE,
            subscription__plan__slug=Plan.SLUG_FAMILIA,
        )
        .select_related('subscription__plan')
        .first()
    )
    return membership.subscription if membership else None
