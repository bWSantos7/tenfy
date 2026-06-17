import re
import unicodedata

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db.models import Func
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .validators import is_valid_cpf, only_digits

User = get_user_model()

CURRENT_CONSENT_VERSION = '1.0.0'


class _NormalizedName(Func):
    """SQL normalização do nome: trim(regexp_replace(unaccent(lower(x)), '\\s+', ' ')).

    Mantém em paridade com ``normalize_full_name`` (lado Python).
    """
    template = "TRIM(REGEXP_REPLACE(UNACCENT(LOWER(%(expressions)s)), '\\s+', ' ', 'g'))"
    arity = 1


def normalize_full_name(name: str) -> str:
    """Normaliza para comparação: sem acento, minúsculo, espaços colapsados."""
    folded = unicodedata.normalize('NFKD', name or '').encode('ascii', 'ignore').decode()
    return re.sub(r'\s+', ' ', folded).strip().lower()


def full_name_taken(name: str, *, exclude_pk=None) -> bool:
    """Task 11: True se já existe usuário com o mesmo nome completo (normalizado).

    Trava absoluta para cadastros novos. Cadastros antigos com nomes iguais
    permanecem (verificação a nível de aplicação, não constraint de banco).
    """
    norm = normalize_full_name(name)
    if not norm:
        return False
    qs = User.objects.annotate(_nn=_NormalizedName('full_name')).filter(_nn=norm)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()

# Base URL for Tênis Integrado player avatar images (external S3 bucket, public CDN).
# Format: {base}/id{ti_id}/fotos/avatar.jpg
_TI_AVATAR_BASE_URL = 'https://tenis-integrado-prod.s3.amazonaws.com/sync-prod'


class UserSerializer(serializers.ModelSerializer):
    managed_by_parent = serializers.SerializerMethodField()
    parent_info = serializers.SerializerMethodField()
    ti_avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id', 'email', 'full_name', 'phone', 'cpf', 'avatar', 'role',
            'email_verified',
            'consent_version', 'consented_at', 'marketing_consent',
            'is_staff', 'is_superuser', 'created_at',
            'managed_by_parent', 'parent_info', 'ti_avatar_url',
        )
        read_only_fields = (
            'id', 'is_staff', 'is_superuser', 'consent_version', 'consented_at', 'created_at',
            'email_verified', 'managed_by_parent', 'parent_info', 'ti_avatar_url',
        )

    def get_ti_avatar_url(self, obj) -> str | None:
        """Return the public TI avatar URL derived from the primary player profile's TI ID."""
        try:
            from apps.players.models import PlayerProfile
            from apps.players.parsers import extract_ti_id
            profile = PlayerProfile.objects.filter(user=obj, is_primary=True).only('external_ids').first()
            if not profile:
                profile = PlayerProfile.objects.filter(user=obj).only('external_ids').first()
            if not profile:
                return None
            ti_id, _ = extract_ti_id(profile.external_ids or {})
            if not ti_id:
                return None
            return f'{_TI_AVATAR_BASE_URL}/id{ti_id}/fotos/avatar.jpg'
        except Exception:
            return None

    def get_managed_by_parent(self, obj) -> bool:
        from .models import ParentChild
        return ParentChild.objects.filter(child=obj, is_active=True).exists()

    def get_parent_info(self, obj):
        from .models import ParentChild
        link = ParentChild.objects.filter(child=obj, is_active=True).select_related('parent').first()
        if not link:
            return None
        return {
            'id': link.parent.id,
            'full_name': link.parent.full_name,
            'email': link.parent.email,
        }


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True, required=True)
    accept_terms = serializers.BooleanField(write_only=True, required=True)
    marketing_consent = serializers.BooleanField(required=False, default=False)
    cpf = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = (
            'email', 'full_name', 'phone', 'cpf', 'role',
            'password', 'password_confirm',
            'accept_terms', 'marketing_consent',
        )
        extra_kwargs = {
            'email': {'required': True},
            'full_name': {'required': False, 'allow_blank': True},
            'phone': {'required': False, 'allow_blank': True},
            'role': {'required': False},
        }

    def validate(self, attrs):
        if attrs['password'] != attrs.pop('password_confirm'):
            raise serializers.ValidationError({'password': 'As senhas não conferem.'})
        if not attrs.pop('accept_terms'):
            raise serializers.ValidationError(
                {'accept_terms': 'É necessário aceitar os termos e a política de privacidade.'}
            )
        # Task 11: nome completo não pode repetir um cadastro existente.
        if full_name_taken(attrs.get('full_name', '')):
            raise serializers.ValidationError(
                {'full_name': 'Já existe um cadastro com este nome completo.'}
            )
        # CPF — opcional no backend, mas validado quando informado (necessário p/ cobrança Asaas).
        cpf_raw = attrs.get('cpf', '')
        if cpf_raw:
            digits = only_digits(cpf_raw)
            if not is_valid_cpf(digits):
                raise serializers.ValidationError({'cpf': 'CPF inválido.'})
            attrs['cpf'] = digits
        else:
            attrs['cpf'] = ''
        return attrs

    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            full_name=validated_data.get('full_name', ''),
            phone=validated_data.get('phone', ''),
            cpf=validated_data.get('cpf', ''),
            role=validated_data.get('role', User.ROLE_PLAYER),
            marketing_consent=validated_data.get('marketing_consent', False),
            consent_version=CURRENT_CONSENT_VERSION,
            consented_at=timezone.now(),
        )
        return user


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['email'] = user.email
        token['role'] = user.role
        token['is_staff'] = user.is_staff
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = UserSerializer(self.user).data
        # Include subscription status so the frontend can gate access immediately
        # without making a separate API call after login.
        try:
            sub = self.user.subscription
            data['subscription_status'] = sub.status
        except Exception:
            data['subscription_status'] = 'none'
        return data


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(required=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({'new_password': 'As senhas não conferem.'})
        return attrs


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('full_name', 'phone', 'role', 'marketing_consent')


class AthleteUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'email', 'full_name', 'avatar', 'role')


class ParentChildSerializer(serializers.ModelSerializer):
    child_detail = AthleteUserSerializer(source='child', read_only=True)

    class Meta:
        from .models import ParentChild
        model = ParentChild
        fields = ('id', 'child', 'child_detail', 'is_active', 'created_at')
        read_only_fields = ('id', 'child', 'child_detail', 'is_active', 'created_at')


class ChildAccountCreateSerializer(serializers.Serializer):
    full_name = serializers.CharField(required=True, max_length=150)
    email = serializers.EmailField(
        required=True,
        error_messages={
            'required': 'Informe o e-mail do dependente.',
            'blank': 'Informe o e-mail do dependente.',
            'invalid': 'Informe um e-mail válido (ex.: nome@dominio.com).',
        },
    )
    phone = serializers.CharField(required=False, allow_blank=True, max_length=20)
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True, required=True)
    # Task 10: código enviado ao e-mail do dependente (request-email-code) que
    # confirma o e-mail antes de criar a conta.
    email_code = serializers.CharField(write_only=True, required=True, max_length=6)

    def validate_email(self, value):
        email = value.lower()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError('Este e-mail já possui cadastro.')
        return email

    def validate(self, attrs):
        from .otp import verify_email_code
        request = self.context['request']
        if request.user.role != User.ROLE_PARENT:
            raise serializers.ValidationError('Apenas responsáveis podem cadastrar filhos.')
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({'password': 'As senhas não conferem.'})
        # Task 11: nome completo do dependente não pode repetir um cadastro existente.
        if full_name_taken(attrs.get('full_name', '')):
            raise serializers.ValidationError(
                {'full_name': 'Já existe um cadastro com este nome completo.'}
            )
        # Confirma o código enviado ao e-mail do dependente.
        if not verify_email_code(attrs['email'], attrs.get('email_code', '')):
            raise serializers.ValidationError(
                {'email_code': 'Código inválido ou expirado. Reenvie o código e tente novamente.'}
            )
        return attrs

    def create(self, validated_data):
        from .models import ParentChild
        parent = self.context['request'].user
        child = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            full_name=validated_data['full_name'],
            phone=validated_data.get('phone', ''),
            role=User.ROLE_PLAYER,
            consent_version=CURRENT_CONSENT_VERSION,
            consented_at=timezone.now(),
        )
        return ParentChild.objects.create(parent=parent, child=child)


class PlayerSearchSerializer(serializers.ModelSerializer):
    """Minimal public data returned when a parent searches for a player to invite.

    The e-mail is masked (e.g. "jo***@gmail.com") so the responsável can recognise
    the right person without the full address being exposed (Task 8: não expor
    dados sensíveis).
    """
    email = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'full_name', 'email', 'avatar', 'role')

    def get_email(self, obj):
        raw = obj.email or ''
        if '@' not in raw:
            return ''
        local, _, domain = raw.partition('@')
        masked_local = (local[:2] + '***') if len(local) > 2 else (local[:1] + '***')
        return f'{masked_local}@{domain}'


class DependentInviteSerializer(serializers.ModelSerializer):
    parent_detail = serializers.SerializerMethodField()
    invitee_detail = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()

    class Meta:
        from .models import DependentInvite
        model = DependentInvite
        fields = (
            'id', 'parent', 'invitee',
            'parent_detail', 'invitee_detail',
            'status', 'is_expired',
            'expires_at', 'responded_at', 'created_at',
        )
        read_only_fields = fields

    def get_parent_detail(self, obj):
        return {'id': obj.parent.id, 'full_name': obj.parent.full_name, 'email': obj.parent.email,
                'avatar': obj.parent.avatar.url if obj.parent.avatar else None}

    def get_invitee_detail(self, obj):
        return {'id': obj.invitee.id, 'full_name': obj.invitee.full_name, 'email': obj.invitee.email,
                'avatar': obj.invitee.avatar.url if obj.invitee.avatar else None}

    def get_is_expired(self, obj) -> bool:
        return obj.is_expired()


class CoachAthleteSerializer(serializers.ModelSerializer):
    athlete_detail = AthleteUserSerializer(source='athlete', read_only=True)
    athlete_email = serializers.EmailField(write_only=True)

    class Meta:
        from .models import CoachAthlete
        model = CoachAthlete
        fields = ('id', 'athlete_detail', 'athlete_email', 'is_active', 'notes', 'created_at')
        read_only_fields = ('id', 'athlete_detail', 'created_at')

    def validate_athlete_email(self, value):
        try:
            athlete = User.objects.get(email=value.lower(), is_active=True)
        except User.DoesNotExist:
            raise serializers.ValidationError('Nenhum usuário encontrado com esse email.')
        return athlete

    def validate(self, attrs):
        coach = self.context['request'].user
        athlete = attrs.get('athlete_email')
        if athlete and athlete == coach:
            raise serializers.ValidationError('Você não pode se adicionar como seu próprio aluno.')
        return attrs

    def create(self, validated_data):
        from .models import CoachAthlete
        athlete = validated_data.pop('athlete_email')
        coach = self.context['request'].user
        obj, created = CoachAthlete.objects.get_or_create(
            coach=coach,
            athlete=athlete,
            defaults={'is_active': True, 'notes': validated_data.get('notes', '')},
        )
        if not created:
            raise serializers.ValidationError('Esse aluno já está na sua lista.')
        return obj
