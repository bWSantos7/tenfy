from django.db import models
from django.contrib.postgres.indexes import GinIndex
from django.utils import timezone
from apps.core.models import TimestampedModel

YOUTH_CIRCUIT_KEYWORDS = {
    'infantojuvenil', 'infanto', 'juvenil', 'junior', 'júnior',
    'sub-', 'kids', 'mirim', 'petiz', 'escola', 'escolinha', 'infantil',
}


class TournamentRegistration(TimestampedModel):
    """
    Inscrição de um jogador (via perfil) em uma edição de torneio.

    Fluxo:
      1. Jogador se inscreve → status pending
      2. Federação confirma pagamento → payment_status = paid
      3. Sistema calcula slot_position pela posição no ranking
      4. Se slot_position <= category.max_participants → in_draw=True
      5. Status final = confirmed / waiting_list / pending_payment / withdrawn
    """

    PAYMENT_PENDING = 'pending'
    PAYMENT_PAID = 'paid'
    PAYMENT_WAIVED = 'waived'
    PAYMENT_REFUNDED = 'refunded'
    PAYMENT_CHOICES = [
        (PAYMENT_PENDING, 'Aguardando pagamento'),
        (PAYMENT_PAID, 'Pago'),
        (PAYMENT_WAIVED, 'Isento'),
        (PAYMENT_REFUNDED, 'Reembolsado'),
    ]

    profile = models.ForeignKey(
        'players.PlayerProfile',
        on_delete=models.CASCADE,
        related_name='registrations',
    )
    edition = models.ForeignKey(
        'tournaments.TournamentEdition',
        on_delete=models.CASCADE,
        related_name='registrations',
    )
    category = models.ForeignKey(
        'tournaments.TournamentCategory',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='registrations',
    )

    registered_at = models.DateTimeField(default=timezone.now, db_index=True)
    ranking_position = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Posição no ranking no momento da inscrição (menor = melhor)',
    )

    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_CHOICES,
        default=PAYMENT_PENDING,
        db_index=True,
    )
    payment_confirmed_at = models.DateTimeField(null=True, blank=True)
    payment_confirmed_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_confirmations',
    )
    payment_notes = models.TextField(blank=True)

    is_withdrawn = models.BooleanField(default=False, db_index=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)

    notes = models.TextField(blank=True, help_text='Observações internas (admin)')

    class Meta:
        ordering = ['ranking_position', 'registered_at']
        unique_together = [('profile', 'edition', 'category')]
        indexes = [
            models.Index(fields=['edition', 'is_withdrawn']),
            models.Index(fields=['profile', 'edition']),
            models.Index(fields=['payment_status']),
        ]

    def __str__(self):
        return f'{self.profile.display_name} @ {self.edition.title}'

    def get_slot_position_label(self, slot_position, max_participants):
        if slot_position is None:
            return '—'
        if max_participants and slot_position <= max_participants:
            return f'#{slot_position} (na chave)'
        return f'#{slot_position} (fora da chave)'

    def withdraw(self):
        self.is_withdrawn = True
        self.withdrawn_at = timezone.now()
        self.save(update_fields=['is_withdrawn', 'withdrawn_at'])

    def confirm_payment(self, confirmed_by=None, notes=''):
        self.payment_status = self.PAYMENT_PAID
        self.payment_confirmed_at = timezone.now()
        if confirmed_by:
            self.payment_confirmed_by = confirmed_by
        if notes:
            self.payment_notes = notes
        fields = ['payment_status', 'payment_confirmed_at', 'payment_confirmed_by', 'payment_notes']
        self.save(update_fields=fields)

    def reset_payment(self):
        self.payment_status = self.PAYMENT_PENDING
        self.payment_confirmed_at = None
        self.payment_confirmed_by = None
        self.save(update_fields=['payment_status', 'payment_confirmed_at', 'payment_confirmed_by'])


class FederationEntry(TimestampedModel):
    """
    Inscrição publicada pela federação para uma edição de torneio.

    Importada via scraping/API das federações (CBT, FPT, FCT, etc.) ou
    entrada manual pelo admin. Contém o nome do jogador, posição no ranking
    e status de pagamento conforme divulgado pela federação.

    Slot position é calculado dinamicamente (não armazenado):
      - Ordenado por ranking_position ASC (nulls last), depois por created_at ASC.
      - in_draw = slot_position <= category.max_participants
      - status: 'confirmed' (pago + in_draw), 'waiting_list' (pago + fora),
                'pending_payment' (não pago), 'withdrawn' (desistência).
    """

    PAYMENT_PAID = 'paid'
    PAYMENT_PENDING = 'pending'
    PAYMENT_UNKNOWN = 'unknown'
    PAYMENT_CHOICES = [
        (PAYMENT_PAID, 'Pago'),
        (PAYMENT_PENDING, 'Pendente'),
        (PAYMENT_UNKNOWN, 'Não informado'),
    ]

    SOURCE_CBT = 'cbt'
    SOURCE_FPT = 'fpt'
    SOURCE_FBT = 'fbt'
    SOURCE_FCT = 'fct'
    SOURCE_COSAT = 'cosat'
    SOURCE_MANUAL = 'manual'

    CONFIDENCE_HIGH = 'high'
    CONFIDENCE_MEDIUM = 'medium'
    CONFIDENCE_LOW = 'low'
    CONFIDENCE_CHOICES = [
        (CONFIDENCE_HIGH, 'Alta — API oficial ou confirmação manual'),
        (CONFIDENCE_MEDIUM, 'Média — scraping de página pública'),
        (CONFIDENCE_LOW, 'Baixa — inferido ou incompleto'),
    ]

    edition = models.ForeignKey(
        'tournaments.TournamentEdition',
        on_delete=models.CASCADE,
        related_name='federation_entries',
    )
    category_text = models.CharField(
        max_length=200,
        help_text='Categoria conforme publicada pela federação (ex: Sub-12 Masculino)',
    )
    player_name = models.CharField(max_length=200)
    player_external_id = models.CharField(
        max_length=100,
        blank=True,
        help_text='ID do jogador na federação de origem',
    )
    ranking_position = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Posição no ranking (menor = melhor)',
    )
    source_order = models.PositiveIntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text='Ordem em que o inscrito aparece na fonte (site). Usada para '
                  'exibir a lista na MESMA ordem do site, em vez de ordenar por '
                  'nome/ranking. Menor = aparece antes.',
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_CHOICES,
        default=PAYMENT_UNKNOWN,
        db_index=True,
    )
    # Substituição por ranking: atleta pago pode ser removido se um atleta de
    # ranking superior se inscrever após o preenchimento das vagas.
    removed_or_replaced = models.BooleanField(
        default=False,
        db_index=True,
        help_text='True se o atleta foi removido/substituído por critério de ranking da federação',
    )
    replacement_reason = models.CharField(
        max_length=300,
        blank=True,
        help_text='Motivo da remoção/substituição conforme publicado pela federação',
    )
    source = models.CharField(
        max_length=50,
        default=SOURCE_MANUAL,
        help_text='Origem: cbt, fpt, fct, cosat, manual…',
    )
    source_url = models.URLField(
        max_length=500,
        blank=True,
        help_text='URL pública onde esta entrada foi encontrada',
    )
    confidence = models.CharField(
        max_length=10,
        choices=CONFIDENCE_CHOICES,
        default=CONFIDENCE_MEDIUM,
        help_text='Grau de confiança nos dados desta entrada',
    )
    notes = models.CharField(max_length=300, blank=True)
    player_country_name = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text='País/nacionalidade do atleta conforme publicado pela fonte (ex: Argentina)',
    )
    player_country_code = models.CharField(
        max_length=10,
        blank=True,
        default='',
        help_text='Código ISO do país (ex: ARG, BR) conforme publicado pela fonte',
    )
    # Dados do atleta exibidos abaixo do nome na lista de inscritos (TASK 6).
    # Preenchidos quando a fonte fornece (Tênis Integrado: id_tenista/uf/idade).
    player_ti_id = models.CharField(
        max_length=20, blank=True, default='',
        help_text='ID do jogador no Tênis Integrado (id_tenista), quando disponível.',
    )
    player_uf = models.CharField(
        max_length=2, blank=True, default='',
        help_text='UF do atleta (ex: SP), quando disponível.',
    )
    player_age = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='Idade do atleta conforme a fonte, quando disponível.',
    )
    # Seção do quadro na fonte (ex.: Main, Qualifying, Alternates). Hoje só o
    # COSAT publica essa divisão; demais fontes ficam com '' (lista única).
    draw_section = models.CharField(
        max_length=40, blank=True, default='',
        help_text='Seção do quadro conforme a fonte (ex.: Main, Qualifying, Alternates).',
    )
    raw_data = models.JSONField(default=dict, blank=True)
    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category_text', 'ranking_position', 'player_name']
        unique_together = [('edition', 'category_text', 'player_external_id', 'source')]
        indexes = [
            models.Index(fields=['edition', 'category_text']),
            models.Index(fields=['payment_status']),
            models.Index(fields=['edition', 'source']),
            # Índice trigram para busca por nome (criado na migration 0009);
            # declarado aqui para o estado do model bater com o do banco.
            GinIndex(fields=['player_name'], name='fedentry_player_name_gin_idx', opclasses=['gin_trgm_ops']),
        ]

    def __str__(self):
        return f'{self.player_name} — {self.category_text} ({self.edition.title})'


class MatchingLog(TimestampedModel):
    """
    Audit trail for the zero-click auto-discovery engine.
    One row per (FederationEntry, matching attempt).
    """

    METHOD_EXTERNAL_ID = 'external_id'
    METHOD_NAME_FUZZY = 'name_fuzzy'
    METHOD_NAME_TOKEN = 'name_token'
    METHOD_NONE = 'none'
    METHOD_CHOICES = [
        (METHOD_EXTERNAL_ID, 'ID externo (match exato)'),
        (METHOD_NAME_FUZZY, 'Nome fuzzy (SequenceMatcher)'),
        (METHOD_NAME_TOKEN, 'Nome por tokens (COSAT/ITF/UTR)'),
        (METHOD_NONE, 'Sem correspondência'),
    ]

    CONFIDENCE_HIGH = 'high'
    CONFIDENCE_MEDIUM = 'medium'
    CONFIDENCE_LOW = 'low'
    CONFIDENCE_NONE = 'none'
    CONFIDENCE_CHOICES = [
        (CONFIDENCE_HIGH, 'Alta'),
        (CONFIDENCE_MEDIUM, 'Média'),
        (CONFIDENCE_LOW, 'Baixa'),
        (CONFIDENCE_NONE, 'Sem match'),
    ]

    entry = models.ForeignKey(
        'FederationEntry',
        on_delete=models.CASCADE,
        related_name='matching_logs',
    )
    profile = models.ForeignKey(
        'players.PlayerProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='matching_logs',
    )
    confidence = models.CharField(
        max_length=10,
        choices=CONFIDENCE_CHOICES,
        default=CONFIDENCE_NONE,
    )
    method = models.CharField(
        max_length=20,
        choices=METHOD_CHOICES,
        default=METHOD_NONE,
    )
    score = models.FloatField(null=True, blank=True)
    registration_created = models.BooleanField(default=False)
    # Motivo legível do match (auditoria): ex. "primeiro nome + último sobrenome
    # iguais; um é abreviação do outro" ou "bloqueado: gênero incompatível".
    match_reason = models.CharField(max_length=300, blank=True, default='')

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['entry']),
            models.Index(fields=['profile']),
        ]

    def __str__(self):
        return f'MatchingLog: {self.entry_id} → profile={self.profile_id} ({self.confidence})'
