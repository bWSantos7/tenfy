from rest_framework import serializers
from apps.tournaments.models import TournamentEdition
from .models import FederationEntry, TournamentRegistration


PAYMENT_STATUS_LABELS = {
    'pending': 'Aguardando pagamento',
    'paid': 'Pago',
    'waived': 'Isento',
    'refunded': 'Reembolsado',
}

REGISTRATION_STATUS_LABELS = {
    'confirmed': 'Confirmado na chave',
    'waiting_list': 'Lista de espera',
    'pending_payment': 'Pagamento pendente',
    'expired': 'Inscrição não confirmada',
    'withdrawn': 'Desistência',
}


def entry_deadline_passed(edition) -> bool:
    """True quando o prazo de inscrição da edição já passou."""
    from django.utils import timezone
    return bool(edition.entry_close_at and edition.entry_close_at < timezone.now())


def compute_registration_status(reg, slot_position, max_participants):
    """Determine the final registration status given position and payment."""
    if reg.is_withdrawn:
        return 'withdrawn'
    payment_confirmed = reg.payment_status in ('paid', 'waived')
    # Aguardando pagamento após o prazo de inscrição → inscrição não confirmada/expirada.
    if not payment_confirmed and entry_deadline_passed(reg.edition):
        return 'expired'
    if max_participants and slot_position and slot_position > max_participants:
        return 'waiting_list'
    if payment_confirmed:
        return 'confirmed'
    return 'pending_payment'


class RegistrationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TournamentRegistration
        fields = ('edition', 'category', 'ranking_position')

    def validate(self, data):
        request = self.context['request']
        profile = self.context.get('profile')
        if not profile:
            raise serializers.ValidationError('Perfil esportivo não encontrado.')
        edition = data['edition']
        category = data.get('category')
        if category and category.edition_id != edition.id:
            raise serializers.ValidationError('Categoria não pertence a esta edição.')
        if TournamentRegistration.objects.filter(
            profile=profile, edition=edition, category=category, is_withdrawn=False
        ).exists():
            raise serializers.ValidationError('Você já está inscrito nesta categoria.')
        return data

    def create(self, validated_data):
        profile = self.context['profile']
        return TournamentRegistration.objects.create(profile=profile, **validated_data)


class MyRegistrationSerializer(serializers.ModelSerializer):
    """Player's own view: shows status + position."""
    edition_id = serializers.IntegerField(source='edition.id', read_only=True)
    edition_title = serializers.CharField(source='edition.title', read_only=True)
    edition_start_date = serializers.DateField(source='edition.start_date', read_only=True)
    edition_end_date = serializers.DateField(source='edition.end_date', read_only=True)
    # Venue location (país/bandeira para torneios internacionais — UTR/ITF/COSAT).
    edition_venue_city = serializers.CharField(source='edition.venue.city', read_only=True, default=None)
    edition_venue_state = serializers.CharField(source='edition.venue.state', read_only=True, default=None)
    edition_venue_country = serializers.CharField(source='edition.venue.country', read_only=True, default=None)
    edition_venue_country_code = serializers.CharField(source='edition.venue.country_code', read_only=True, default=None)
    edition_status = serializers.SerializerMethodField()
    is_past = serializers.SerializerMethodField()
    category_text = serializers.SerializerMethodField()
    max_participants = serializers.SerializerMethodField()
    slot_position = serializers.SerializerMethodField()
    in_draw = serializers.SerializerMethodField()
    registration_status = serializers.SerializerMethodField()
    registration_status_label = serializers.SerializerMethodField()
    payment_status_label = serializers.SerializerMethodField()

    class Meta:
        model = TournamentRegistration
        fields = (
            'id', 'edition_id', 'edition_title', 'edition_start_date', 'edition_end_date',
            'edition_venue_city', 'edition_venue_state',
            'edition_venue_country', 'edition_venue_country_code',
            'edition_status', 'is_past', 'category_text', 'max_participants',
            'registered_at', 'ranking_position',
            'payment_status', 'payment_status_label', 'payment_confirmed_at',
            'is_withdrawn', 'withdrawn_at',
            'slot_position', 'in_draw',
            'registration_status', 'registration_status_label',
        )

    def get_edition_status(self, obj):
        return obj.edition.compute_dynamic_status()

    def get_is_past(self, obj):
        """True quando o torneio já terminou ou foi cancelado.

        Fonte da verdade para 'Inscrições ativas': uma inscrição em torneio
        passado/cancelado nunca deve ser exibida como ativa, mesmo que esteja
        paga/confirmada.
        """
        return obj.edition.compute_dynamic_status() in (
            TournamentEdition.STATUS_FINISHED,
            TournamentEdition.STATUS_CANCELED,
        )

    def get_category_text(self, obj):
        return obj.category.source_category_text if obj.category else None

    def get_max_participants(self, obj):
        return obj.category.max_participants if obj.category else None

    def get_slot_position(self, obj):
        return getattr(obj, 'slot_position', None)

    def get_in_draw(self, obj):
        slot = getattr(obj, 'slot_position', None)
        max_p = obj.category.max_participants if obj.category else None
        if slot is None:
            return None
        if max_p is None:
            return True
        return slot <= max_p

    def get_registration_status(self, obj):
        slot = getattr(obj, 'slot_position', None)
        max_p = obj.category.max_participants if obj.category else None
        return compute_registration_status(obj, slot, max_p)

    def get_registration_status_label(self, obj):
        return REGISTRATION_STATUS_LABELS.get(self.get_registration_status(obj), '')

    def get_payment_status_label(self, obj):
        return PAYMENT_STATUS_LABELS.get(obj.payment_status, obj.payment_status)


class AdminRegistrationSerializer(serializers.ModelSerializer):
    """Admin view: full detail with player info and payment actions."""
    player_name = serializers.CharField(source='profile.display_name', read_only=True)
    player_user_email = serializers.EmailField(source='profile.user.email', read_only=True)
    player_gender = serializers.CharField(source='profile.gender', read_only=True)
    player_birth_year = serializers.IntegerField(source='profile.birth_year', read_only=True)
    player_sporting_age = serializers.IntegerField(source='profile.sporting_age', read_only=True)
    category_text = serializers.SerializerMethodField()
    max_participants = serializers.SerializerMethodField()
    slot_position = serializers.SerializerMethodField()
    in_draw = serializers.SerializerMethodField()
    registration_status = serializers.SerializerMethodField()
    registration_status_label = serializers.SerializerMethodField()
    payment_status_label = serializers.SerializerMethodField()
    payment_confirmed_by_email = serializers.EmailField(
        source='payment_confirmed_by.email', read_only=True, default=None
    )

    class Meta:
        model = TournamentRegistration
        fields = (
            'id', 'profile', 'player_name', 'player_user_email',
            'player_gender', 'player_birth_year', 'player_sporting_age',
            'edition', 'category', 'category_text', 'max_participants',
            'registered_at', 'ranking_position',
            'payment_status', 'payment_status_label',
            'payment_confirmed_at', 'payment_confirmed_by', 'payment_confirmed_by_email',
            'payment_notes',
            'is_withdrawn', 'withdrawn_at', 'notes',
            'slot_position', 'in_draw',
            'registration_status', 'registration_status_label',
            'created_at', 'updated_at',
        )

    def get_category_text(self, obj):
        return obj.category.source_category_text if obj.category else None

    def get_max_participants(self, obj):
        return obj.category.max_participants if obj.category else None

    def get_slot_position(self, obj):
        return getattr(obj, 'slot_position', None)

    def get_in_draw(self, obj):
        slot = getattr(obj, 'slot_position', None)
        max_p = obj.category.max_participants if obj.category else None
        if slot is None:
            return None
        if max_p is None:
            return True
        return slot <= max_p

    def get_registration_status(self, obj):
        slot = getattr(obj, 'slot_position', None)
        max_p = obj.category.max_participants if obj.category else None
        return compute_registration_status(obj, slot, max_p)

    def get_registration_status_label(self, obj):
        return REGISTRATION_STATUS_LABELS.get(self.get_registration_status(obj), '')

    def get_payment_status_label(self, obj):
        return PAYMENT_STATUS_LABELS.get(obj.payment_status, obj.payment_status)


class BulkPaymentSerializer(serializers.Serializer):
    registration_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1)
    payment_status = serializers.ChoiceField(choices=TournamentRegistration.PAYMENT_CHOICES)
    notes = serializers.CharField(required=False, allow_blank=True, default='')


# ─── Federation Entry ──────────────────────────────────────────────────────────

FED_PAYMENT_LABELS = {
    'paid': 'Pago',
    'pending': 'Aguardando pagamento',
    'unknown': 'Não informado',
}

FED_STATUS_LABELS = {
    'confirmed':       'Confirmado na chave',
    'waiting_list':    'Lista de espera',
    'pending_payment': 'Aguardando pagamento',
    'removed':         'Removido — critério de ranking',
    # COSAT and other international sources that don't expose payment info
    'registered':      'Inscrito',
}

SOURCE_LABELS = {
    'cbt':    'CBT',
    'fbt':    'FBT',
    'fpt':    'FPT',
    'fct':    'FCT',
    'cosat':  'COSAT',
    'manual': 'Importação manual',
}


def compute_fed_status(payment_status: str, slot_position, max_participants,
                       removed_or_replaced: bool = False) -> str:
    """
    Calcula status final de um inscrito externo (FederationEntry).

    Regra de substituição: um atleta PAGO pode ser removido se a federação
    aplicar critério de ranking e um atleta com ranking melhor se inscrever
    após o preenchimento das vagas. Nesse caso, payment_status='paid' NÃO
    garante 'confirmed' — o campo removed_or_replaced prevalece.
    """
    if removed_or_replaced:
        return 'removed'
    if max_participants and slot_position and slot_position > max_participants:
        return 'waiting_list'
    if payment_status == FederationEntry.PAYMENT_PAID:
        return 'confirmed'
    return 'pending_payment'


class FederationEntrySerializer(serializers.ModelSerializer):
    slot_position       = serializers.SerializerMethodField()
    in_draw             = serializers.SerializerMethodField()
    status              = serializers.SerializerMethodField()
    status_label        = serializers.SerializerMethodField()
    payment_status_label = serializers.SerializerMethodField()
    source_label        = serializers.SerializerMethodField()

    class Meta:
        model = FederationEntry
        fields = (
            'id', 'category_text', 'player_name', 'player_external_id',
            'ranking_position', 'payment_status', 'payment_status_label',
            'source', 'source_label', 'source_url', 'confidence',
            'removed_or_replaced', 'replacement_reason',
            'player_country_name', 'player_country_code',
            'notes', 'synced_at',
            'slot_position', 'in_draw', 'status', 'status_label',
        )

    def _max_p(self, obj):
        return getattr(obj, '_max_participants', None)

    def get_slot_position(self, obj):
        return getattr(obj, 'slot_position', None)

    def get_in_draw(self, obj):
        if obj.removed_or_replaced:
            return False
        slot = getattr(obj, 'slot_position', None)
        max_p = self._max_p(obj)
        if slot is None:
            return None
        return (max_p is None) or (slot <= max_p)

    def get_status(self, obj):
        if obj.removed_or_replaced:
            return 'removed'
        # COSAT (and other international sources) don't track payment.
        # unknown payment on COSAT = registered but payment N/A, not pending.
        if obj.source == FederationEntry.SOURCE_COSAT and obj.payment_status == FederationEntry.PAYMENT_UNKNOWN:
            return 'registered'
        slot = getattr(obj, 'slot_position', None)
        return compute_fed_status(
            obj.payment_status, slot, self._max_p(obj),
            removed_or_replaced=obj.removed_or_replaced,
        )

    def get_status_label(self, obj):
        return FED_STATUS_LABELS.get(self.get_status(obj), 'Desconhecido')

    def get_payment_status_label(self, obj):
        return FED_PAYMENT_LABELS.get(obj.payment_status, obj.payment_status)

    def get_source_label(self, obj):
        return SOURCE_LABELS.get(obj.source, obj.source)


class FederationEntryWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = FederationEntry
        fields = (
            'edition', 'category_text', 'player_name', 'player_external_id',
            'ranking_position', 'payment_status', 'source', 'source_url',
            'confidence', 'removed_or_replaced', 'replacement_reason', 'notes',
            'player_country_name', 'player_country_code',
        )
