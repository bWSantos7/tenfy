"""
Referrals — Programa de cupons, indicação e comissão de parceiros.

Domínio (PRD §18 / estados §17):
  Partner          — parceiro que indica (influenciador, treinador, academia, embaixador).
  Coupon           — cupom de desconto vinculado a um único parceiro (RN-001).
  CommissionRule   — regra de comissão (percentual ou fixa) por parceiro/cupom.
  CommissionLedger — lançamento de comissão gerado após pagamento confirmado.
  Payout           — repasse manual consolidado por parceiro (MVP).

Decisões fixadas:
  - Comissão incide sobre o valor líquido pago (RN-006) e só no 1º pagamento confirmado (RN-010).
  - 1 parceiro comissionável por assinatura (RN-004) — FK única em billing.Subscription.
  - 1 comissão por pagamento (RF-013) — unique em CommissionLedger.payment.

Referências a billing.* são por string para evitar import circular
(billing.Subscription também referencia referrals.Partner/Coupon).
"""
from decimal import Decimal

from django.db import models

from apps.core.models import TimestampedModel


# ── Parceiro ─────────────────────────────────────────────────────────────────────

class Partner(TimestampedModel):
    TYPE_INFLUENCER = 'influencer'
    TYPE_COACH      = 'coach'
    TYPE_ACADEMY    = 'academy'
    TYPE_AMBASSADOR = 'ambassador'
    TYPE_OTHER      = 'other'
    TYPE_CHOICES = [
        (TYPE_INFLUENCER, 'Influenciador'),
        (TYPE_COACH,      'Treinador'),
        (TYPE_ACADEMY,    'Academia'),
        (TYPE_AMBASSADOR, 'Embaixador'),
        (TYPE_OTHER,      'Outro'),
    ]

    STATUS_ACTIVE   = 'active'
    STATUS_INACTIVE = 'inactive'
    STATUS_CHOICES = [
        (STATUS_ACTIVE,   'Ativo'),
        (STATUS_INACTIVE, 'Inativo'),
    ]

    PAYOUT_PIX    = 'pix'
    PAYOUT_BANK   = 'bank_transfer'
    PAYOUT_MANUAL = 'manual'
    PAYOUT_CHOICES = [
        (PAYOUT_PIX,    'Pix'),
        (PAYOUT_BANK,   'Transferência bancária'),
        (PAYOUT_MANUAL, 'Manual / a combinar'),
    ]

    # Conta de login do parceiro (role=partner). Criada/gerida pelo admin.
    # SET_NULL: remover a conta não apaga o histórico do parceiro.
    user          = models.OneToOneField(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='partner_account',
    )
    name          = models.CharField(max_length=120)
    type          = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_OTHER)
    email         = models.EmailField(blank=True)
    phone         = models.CharField(max_length=30, blank=True)
    status        = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    payout_method = models.CharField(max_length=20, choices=PAYOUT_CHOICES, blank=True)
    # Dados de repasse (PIX/chave/banco). Sem PII sensível além do necessário (LGPD).
    payout_details = models.CharField(max_length=200, blank=True, help_text='Chave Pix ou dados de repasse')
    notes         = models.TextField(blank=True)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['type']),
        ]

    def __str__(self):
        return f'{self.name} ({self.get_type_display()})'

    @property
    def is_active(self) -> bool:
        return self.status == self.STATUS_ACTIVE


# ── Cupom ────────────────────────────────────────────────────────────────────────

class Coupon(TimestampedModel):
    DISCOUNT_PERCENT = 'percent'
    DISCOUNT_FIXED   = 'fixed'
    DISCOUNT_CHOICES = [
        (DISCOUNT_PERCENT, 'Percentual (%)'),
        (DISCOUNT_FIXED,   'Valor fixo (R$)'),
    ]

    SCOPE_INDIVIDUAL = 'individual'
    SCOPE_FAMILIA    = 'familia'
    SCOPE_BOTH       = 'both'
    SCOPE_CHOICES = [
        (SCOPE_INDIVIDUAL, 'Apenas Individual'),
        (SCOPE_FAMILIA,    'Apenas Família'),
        (SCOPE_BOTH,       'Individual e Família'),
    ]

    STATUS_DRAFT     = 'draft'
    STATUS_ACTIVE    = 'active'
    STATUS_INACTIVE  = 'inactive'
    STATUS_EXPIRED   = 'expired'
    STATUS_EXHAUSTED = 'exhausted'
    STATUS_CHOICES = [
        (STATUS_DRAFT,     'Rascunho'),
        (STATUS_ACTIVE,    'Ativo'),
        (STATUS_INACTIVE,  'Inativo'),
        (STATUS_EXPIRED,   'Expirado'),
        (STATUS_EXHAUSTED, 'Esgotado'),
    ]

    code            = models.CharField(max_length=40, unique=True)
    partner         = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name='coupons')
    discount_type   = models.CharField(max_length=10, choices=DISCOUNT_CHOICES, default=DISCOUNT_PERCENT)
    discount_value  = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    plan_scope      = models.CharField(max_length=12, choices=SCOPE_CHOICES, default=SCOPE_BOTH)
    starts_at       = models.DateTimeField(null=True, blank=True)
    expires_at      = models.DateTimeField(null=True, blank=True)
    # NULL = ilimitado
    max_total_uses        = models.PositiveIntegerField(null=True, blank=True, help_text='NULL = ilimitado')
    max_uses_per_customer = models.PositiveIntegerField(default=1, help_text='Usos por cliente (0/NULL = ilimitado)', null=True, blank=True)
    times_used      = models.PositiveIntegerField(default=0, help_text='Total de aplicações confirmadas (denormalizado)')
    status          = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_DRAFT)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f'{self.code} → {self.partner.name}'

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def scope_allows_plan(self, plan_slug: str) -> bool:
        if self.plan_scope == self.SCOPE_BOTH:
            return plan_slug in ('individual', 'familia')
        return self.plan_scope == plan_slug


# ── Regra de comissão ────────────────────────────────────────────────────────────

class CommissionRule(TimestampedModel):
    COMMISSION_PERCENT = 'percent'
    COMMISSION_FIXED   = 'fixed'
    COMMISSION_CHOICES = [
        (COMMISSION_PERCENT, 'Percentual (%)'),
        (COMMISSION_FIXED,   'Valor fixo (R$)'),
    ]

    SCOPE_FIRST_PAYMENT = 'first_payment'
    SCOPE_ALL_PAYMENTS  = 'all_payments'
    SCOPE_CHOICES = [
        (SCOPE_FIRST_PAYMENT, 'Apenas 1º pagamento'),
        (SCOPE_ALL_PAYMENTS,  'Todos os pagamentos'),
    ]

    BASE_NET   = 'net_paid'
    BASE_GROSS = 'gross_paid'
    BASE_CHOICES = [
        (BASE_NET,   'Valor líquido pago'),
        (BASE_GROSS, 'Valor bruto pago'),
    ]

    STATUS_ACTIVE   = 'active'
    STATUS_INACTIVE = 'inactive'
    STATUS_CHOICES = [
        (STATUS_ACTIVE,   'Ativa'),
        (STATUS_INACTIVE, 'Inativa'),
    ]

    partner          = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name='commission_rules')
    coupon           = models.ForeignKey(
        Coupon, null=True, blank=True, on_delete=models.CASCADE, related_name='commission_rules',
        help_text='Vazio = regra padrão do parceiro',
    )
    commission_type  = models.CharField(max_length=10, choices=COMMISSION_CHOICES, default=COMMISSION_PERCENT)
    commission_value = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    # MVP: comissão só no 1º pagamento (RN-010)
    rule_scope       = models.CharField(max_length=15, choices=SCOPE_CHOICES, default=SCOPE_FIRST_PAYMENT)
    # MVP: base = valor líquido pago (RN-006)
    base_amount_type = models.CharField(max_length=12, choices=BASE_CHOICES, default=BASE_NET)
    status           = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
        ]

    def __str__(self):
        unit = '%' if self.commission_type == self.COMMISSION_PERCENT else 'R$'
        target = self.coupon.code if self.coupon_id else 'padrão'
        return f'{self.partner.name} [{target}] {self.commission_value}{unit}'

    def compute(self, base_amount: Decimal) -> Decimal:
        """Calcula o valor da comissão sobre a base informada."""
        base = Decimal(base_amount or 0)
        if self.commission_type == self.COMMISSION_PERCENT:
            return (base * Decimal(self.commission_value) / Decimal('100')).quantize(Decimal('0.01'))
        return Decimal(self.commission_value).quantize(Decimal('0.01'))


# ── Repasse (payout) ─────────────────────────────────────────────────────────────

class Payout(TimestampedModel):
    STATUS_DRAFT      = 'draft'
    STATUS_PROCESSING = 'processing'
    STATUS_PAID       = 'paid'
    STATUS_FAILED     = 'failed'
    STATUS_CANCELED   = 'canceled'
    STATUS_CHOICES = [
        (STATUS_DRAFT,      'Rascunho'),
        (STATUS_PROCESSING, 'Processando'),
        (STATUS_PAID,       'Pago'),
        (STATUS_FAILED,     'Falhou'),
        (STATUS_CANCELED,   'Cancelado'),
    ]

    partner   = models.ForeignKey(Partner, on_delete=models.PROTECT, related_name='payouts')
    amount    = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status    = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    method    = models.CharField(max_length=20, blank=True, help_text='Método de repasse usado')
    reference = models.CharField(max_length=120, blank=True, help_text='Comprovante/ID do repasse manual')
    notes     = models.TextField(blank=True)
    paid_at   = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['partner', '-created_at']),
        ]

    def __str__(self):
        return f'Repasse R${self.amount} → {self.partner.name} [{self.status}]'


# ── Lançamento de comissão (ledger) ──────────────────────────────────────────────

class CommissionLedger(TimestampedModel):
    STATUS_PENDING  = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_PAID     = 'paid'
    STATUS_REVERSED = 'reversed'
    STATUS_CANCELED = 'canceled'
    STATUS_CHOICES = [
        (STATUS_PENDING,  'Pendente'),
        (STATUS_APPROVED, 'Aprovada'),
        (STATUS_PAID,     'Paga'),
        (STATUS_REVERSED, 'Revertida'),
        (STATUS_CANCELED, 'Cancelada'),
    ]

    partner         = models.ForeignKey(Partner, on_delete=models.PROTECT, related_name='commissions')
    coupon          = models.ForeignKey(
        Coupon, null=True, blank=True, on_delete=models.SET_NULL, related_name='commissions',
    )
    subscription    = models.ForeignKey(
        'billing.Subscription', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='commissions',
    )
    # 1 comissão por pagamento (RF-013): unique garante idempotência.
    payment         = models.OneToOneField(
        'billing.Payment', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='commission',
    )
    commission_rule = models.ForeignKey(
        CommissionRule, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='commissions',
    )
    payout          = models.ForeignKey(
        Payout, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='commissions',
    )
    base_amount       = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status            = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['payment'],
                condition=models.Q(payment__isnull=False),
                name='uniq_commission_per_payment',
            ),
        ]
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['partner', 'status']),
        ]

    def __str__(self):
        return f'Comissão R${self.commission_amount} → {self.partner.name} [{self.status}]'
