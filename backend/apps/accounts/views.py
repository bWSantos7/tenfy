import ipaddress
import logging
import secrets

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken

from rest_framework import viewsets
from rest_framework.decorators import action as viewset_action
from .serializers import (
    RegisterSerializer,
    UserSerializer,
    UserUpdateSerializer,
    CustomTokenObtainPairSerializer,
    PasswordChangeSerializer,
    CoachAthleteSerializer,
    ChildAccountCreateSerializer,
    ParentChildSerializer,
    DependentInviteSerializer,
    PlayerSearchSerializer,
)
from .models import CoachAthlete, ParentChild, DependentInvite

logger = logging.getLogger('apps.accounts')

User = get_user_model()


def _resolve_federation(federation_value):
    """Resolve a federation id (from raw profile payload) to an active federation
    Organization, or None. Tolerant: invalid/missing ids return None so federation
    stays optional and never blocks profile creation."""
    if not federation_value:
        return None
    from apps.sources.models import Organization
    try:
        return Organization.objects.get(
            pk=int(federation_value),
            type=Organization.TYPE_FEDERATION,
            is_active=True,
        )
    except (Organization.DoesNotExist, ValueError, TypeError):
        return None


def _send_email_otp_with_fallback(user, subject_key='verify') -> bool:
    """
    Generate and dispatch an email OTP.

    Celery broker outages should not turn account creation into a 500. Try the
    normal async path first, then execute the task locally as a fallback.
    """
    from .otp import generate_and_store
    from .tasks import send_otp_email

    code = generate_and_store(user.id, 'email')
    args = (user.id, user.email, user.full_name or '', code, subject_key)

    try:
        send_otp_email.delay(*args)
        return True
    except Exception as exc:
        logger.warning(
            'OTP email enqueue failed for user %s; trying synchronous fallback: %s',
            user.id,
            exc,
        )

    try:
        result = send_otp_email.apply(args=args)
        if hasattr(result, 'get'):
            result.get(propagate=True)
        logger.info('OTP email sent synchronously for user %s', user.id)
        return True
    except Exception as exc:
        logger.error('OTP email dispatch failed for user %s: %s', user.id, exc)
        return False


def _send_dependent_email_code(email: str) -> bool:
    """Generate + dispatch a confirmation code to a (not-yet-registered) dependent
    e-mail. Same Celery-with-sync-fallback strategy as the user OTP. user_id=0 is a
    placeholder — the task only uses it for logging, not a DB lookup."""
    from .otp import generate_email_code
    from .tasks import send_otp_email

    code = generate_email_code(email)
    args = (0, email, '', code, 'dependent')
    try:
        send_otp_email.delay(*args)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning('Dependent OTP enqueue failed; sync fallback: %s', exc)
    try:
        result = send_otp_email.apply(args=args)
        if hasattr(result, 'get'):
            result.get(propagate=True)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error('Dependent OTP dispatch failed: %s', exc)
        return False


class RegisterThrottle(AnonRateThrottle):
    rate = '10/hour'


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [RegisterThrottle]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)

        otp_sent = _send_email_otp_with_fallback(user, 'verify')

        return Response({
            'user': UserSerializer(user, context={'request': request}).data,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'email_otp_sent': otp_sent,
        }, status=status.HTTP_201_CREATED)


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            ip = self._get_ip(request)
            email = request.data.get('email', '').strip().lower()
            if email:
                try:
                    user = User.objects.get(email=email)
                    user.last_login = timezone.now()
                    user.last_login_ip = ip
                    user.save(update_fields=['last_login', 'last_login_ip'])
                except User.DoesNotExist:
                    pass
        return response

    @staticmethod
    def _get_ip(request):
        xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if xff:
            candidate = xff.split(',')[0].strip()
            try:
                ipaddress.ip_address(candidate)
                return candidate
            except ValueError:
                pass
        return request.META.get('REMOTE_ADDR', '')


class MeView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        if self.request.method in ['PATCH', 'PUT']:
            return UserUpdateSerializer
        return UserSerializer

    def update(self, request, *args, **kwargs):
        super().update(request, *args, **kwargs)
        return Response(UserSerializer(self.get_object(), context={'request': request}).data)


_ALLOWED_IMAGE_FORMATS = {'JPEG', 'PNG', 'WEBP', 'GIF'}
_MAX_AVATAR_BYTES = 1 * 1024 * 1024  # 1 MB — reduced to control Cloudinary bandwidth


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def upload_avatar(request):
    """
    Upload or replace the user's avatar image.

    Security: validates magic bytes via Pillow (not just Content-Type header),
    rejects SVG and any non-raster format to prevent script injection.
    """
    file = request.FILES.get('avatar')
    if not file:
        return Response({'detail': 'Nenhuma imagem enviada.'}, status=status.HTTP_400_BAD_REQUEST)

    if file.size > _MAX_AVATAR_BYTES:
        return Response({'detail': 'Imagem deve ter no máximo 1MB.'}, status=status.HTTP_400_BAD_REQUEST)

    # Reject SVG by content_type before reading bytes (fast path)
    if file.content_type in ('image/svg+xml', 'image/svg', 'text/xml', 'text/html'):
        return Response({'detail': 'Formato SVG não é permitido.'}, status=status.HTTP_400_BAD_REQUEST)

    # Validate magic bytes with Pillow — rejects disguised executables and SVGs
    try:
        from PIL import Image
        img = Image.open(file)
        img.verify()  # raises if not a valid image
        if img.format not in _ALLOWED_IMAGE_FORMATS:
            return Response(
                {'detail': f'Formato {img.format} não suportado. Use JPEG, PNG, WEBP ou GIF.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Reset file pointer after verify() consumed the stream
        file.seek(0)
    except Exception:
        return Response({'detail': 'Arquivo inválido ou corrompido.'}, status=status.HTTP_400_BAD_REQUEST)

    user = request.user
    if user.avatar:
        user.avatar.delete(save=False)
    user.avatar = file
    user.save(update_fields=['avatar'])
    return Response(UserSerializer(user, context={'request': request}).data)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def change_password(request):
    serializer = PasswordChangeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = request.user
    if not user.check_password(serializer.validated_data['old_password']):
        return Response(
            {'old_password': 'Senha atual incorreta.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    user.set_password(serializer.validated_data['new_password'])
    user.save()
    return Response({'detail': 'Senha alterada com sucesso.'})


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def logout(request):
    try:
        refresh_token = request.data.get('refresh')
        if refresh_token:
            token = RefreshToken(refresh_token)
            token.blacklist()
        return Response({'detail': 'Logout realizado.'}, status=status.HTTP_205_RESET_CONTENT)
    except Exception:
        return Response({'detail': 'Logout realizado.'}, status=status.HTTP_205_RESET_CONTENT)


@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def delete_account(request):
    """
    LGPD Art. 18: anonimização real — remove todos os dados pessoais identificáveis.
    Registros financeiros e de auditoria são mantidos com referência anonimizada.
    """
    user = request.user
    anon_token = secrets.token_hex(16)

    with transaction.atomic():
        # Invalidate all JWT tokens by blacklisting every outstanding token
        try:
            from rest_framework_simplejwt.token_blacklist.models import (
                BlacklistedToken,
                OutstandingToken,
            )
            for outstanding in OutstandingToken.objects.filter(user=user):
                BlacklistedToken.objects.get_or_create(token=outstanding)
        except Exception:
            pass

        # Anonymize the user record — keep row for FK integrity in payments/audit
        user.email = f'deleted-{anon_token}@anon.invalid'
        user.full_name = '[Removido]'
        user.phone = ''
        user.avatar = None
        user.is_active = False
        user.set_unusable_password()
        user.save(update_fields=[
            'email', 'full_name', 'phone', 'avatar',
            'is_active', 'password',
        ])

        # Remove player profiles (personal data)
        try:
            from apps.players.models import PlayerProfile
            PlayerProfile.objects.filter(user=user).delete()
        except Exception:
            pass

        # Remove push subscriptions
        try:
            from apps.alerts.models import PushSubscription
            PushSubscription.objects.filter(user=user).delete()
        except Exception:
            pass

        logger.info('Account anonymized for user_id=%s (LGPD)', user.id)

    return Response({'detail': 'Conta removida com sucesso.'}, status=status.HTTP_204_NO_CONTENT)


class OtpThrottle(AnonRateThrottle):
    rate = '10/hour'


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@throttle_classes([OtpThrottle])
def send_email_otp(request):
    """Send 6-digit OTP to the authenticated user's email via Celery (auto-retries)."""
    user = request.user
    if not _send_email_otp_with_fallback(user, 'resend'):
        return Response(
            {'detail': 'Não foi possível enviar o código agora. Tente novamente em instantes.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return Response({'detail': f'Código enviado para {user.email}.'})


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def verify_email_otp(request):
    """Verify email OTP and mark user's email as verified."""
    from .otp import verify
    code = (request.data.get('code') or '').strip()
    if not code:
        return Response({'detail': 'Código obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)
    if verify(request.user.id, 'email', code):
        request.user.email_verified = True
        request.user.save(update_fields=['email_verified', 'updated_at'])
        return Response({'detail': 'E-mail verificado com sucesso.'})
    return Response({'detail': 'Código inválido ou expirado.'}, status=status.HTTP_400_BAD_REQUEST)



class PasswordResetRequestThrottle(AnonRateThrottle):
    rate = '5/hour'


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
@throttle_classes([PasswordResetRequestThrottle])
def password_reset_request(request):
    """Envia email com link para redefinição de senha."""
    email = (request.data.get('email') or '').strip().lower()
    if not email:
        return Response({'detail': 'Email obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)

    # Always return 200 to avoid user enumeration
    try:
        user = User.objects.get(email=email, is_active=True)
    except User.DoesNotExist:
        return Response({'detail': 'Se o email existir, enviaremos as instruções.'})

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
    reset_url = f'{frontend_url}/redefinir-senha/{uid}/{token}/'

    # SECURITY: never log the full reset URL — token is a credential
    logger.info('Password reset requested for user %s', user.id)

    # Dispatch via Celery — synchronous fallback when broker is unavailable.
    # reset_url contains uid+token: never log it.
    from .tasks import send_password_reset_email
    args = (user.id, user.email, user.full_name or '', reset_url)
    try:
        send_password_reset_email.delay(*args)
    except Exception as exc:
        logger.warning(
            'Password reset email enqueue failed for user %s; trying synchronous fallback: %s',
            user.id, exc,
        )
        try:
            result = send_password_reset_email.apply(args=args)
            if hasattr(result, 'get'):
                result.get(propagate=True)
        except Exception as exc2:
            logger.error('Password reset email dispatch failed for user %s: %s', user.id, exc2)

    return Response({'detail': 'Se o email existir, enviaremos as instruções.'})


class IsCoach(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'coach'


class CoachAthleteViewSet(viewsets.ModelViewSet):
    """Coaches manage their athlete roster and view athletes' watchlists."""
    serializer_class = CoachAthleteSerializer
    permission_classes = [IsCoach]
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        return (
            CoachAthlete.objects
            .filter(coach=self.request.user)
            .select_related('athlete')
            .order_by('-created_at')
        )

    @viewset_action(detail=True, methods=['get'], url_path='watchlist')
    def athlete_watchlist(self, request, pk=None):
        """Return watchlist items for one of the coach's athletes."""
        from apps.watchlist.models import WatchlistItem
        from apps.watchlist.serializers import WatchlistItemSerializer
        link = self.get_object()
        qs = (
            WatchlistItem.objects
            .filter(user=link.athlete)
            .select_related('edition__tournament__organization', 'edition__venue', 'profile')
            .order_by('-created_at')
        )
        serializer = WatchlistItemSerializer(qs, many=True, context={'request': request})
        return Response({'athlete': link.athlete.email, 'watchlist': serializer.data})


class IsParent(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == User.ROLE_PARENT


class ParentChildViewSet(viewsets.ModelViewSet):
    """Parents create and manage child player accounts."""
    permission_classes = [IsParent]
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        return (
            ParentChild.objects
            .filter(parent=self.request.user, is_active=True)
            .select_related('child')
            .order_by('-created_at')
        )

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ChildAccountCreateSerializer
        return ParentChildSerializer

    def destroy(self, request, *args, **kwargs):
        return Response(
            {'detail': 'Para remover um dependente use DELETE /children/{id}/remove/.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def create(self, request, *args, **kwargs):
        # Enforce plan-based dependent limit
        from apps.billing.models import Subscription, Plan
        current_dependents = ParentChild.objects.filter(parent=request.user, is_active=True).count()

        try:
            sub = request.user.subscription
            if sub.plan.slug == Plan.SLUG_INDIVIDUAL:
                return Response(
                    {'detail': 'O Plano Individual não permite cadastrar dependentes. Faça upgrade para o Plano Família.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            max_dependents = sub.plan.max_members - 1  # titular doesn't count
            if current_dependents >= max_dependents:
                return Response(
                    {'detail': f'Limite de {max_dependents} dependente(s) atingido para o seu plano. Faça upgrade para adicionar mais.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except Subscription.DoesNotExist:
            # Allow first dependent creation for parent accounts during initial onboarding.
            # Subsequent dependents require an active Família subscription.
            if current_dependents >= 1:
                return Response(
                    {'detail': 'Você precisa de uma assinatura ativa do Plano Família para adicionar mais dependentes.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        link = serializer.save()
        return Response(
            ParentChildSerializer(link, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

    @viewset_action(detail=False, methods=['post'], url_path='create-with-profile')
    def create_with_profile(self, request):
        """Atomically create a child account and sports profile in a single request."""
        from django.db import transaction
        from apps.players.models import PlayerProfile

        if request.user.role != 'parent':
            return Response(
                {'detail': 'Apenas contas do tipo Responsável/Pai podem cadastrar dependentes.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        from apps.billing.models import Subscription, Plan
        current_dependents = ParentChild.objects.filter(parent=request.user, is_active=True).count()
        if not request.user.is_staff:
            try:
                sub = request.user.subscription
                if sub.plan.slug == Plan.SLUG_INDIVIDUAL:
                    return Response(
                        {'detail': 'O Plano Individual não permite cadastrar dependentes. Faça upgrade para o Plano Família.'},
                        status=status.HTTP_403_FORBIDDEN,
                    )
                max_dependents = sub.plan.max_members - 1
                if current_dependents >= max_dependents:
                    return Response(
                        {'detail': f'Limite de {max_dependents} dependente(s) atingido para o seu plano.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except Subscription.DoesNotExist:
                if current_dependents >= 1:
                    return Response(
                        {'detail': 'Você precisa de uma assinatura ativa do Plano Família para adicionar mais dependentes.'},
                        status=status.HTTP_403_FORBIDDEN,
                    )

        account_serializer = ChildAccountCreateSerializer(data=request.data, context={'request': request})
        account_serializer.is_valid(raise_exception=True)

        profile_data = request.data.get('profile')
        if not isinstance(profile_data, dict):
            return Response(
                {'profile': 'O perfil esportivo do dependente é obrigatório.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        profile_errors = {}
        if not profile_data.get('birth_year'):
            profile_errors['birth_year'] = 'Este campo é obrigatório.'
        if not profile_data.get('gender'):
            profile_errors['gender'] = 'Este campo é obrigatório.'
        if not profile_data.get('home_state'):
            profile_errors['home_state'] = 'Este campo é obrigatório.'
        if not profile_data.get('competitive_level'):
            profile_errors['competitive_level'] = 'Este campo é obrigatório.'
        if profile_errors:
            return Response({'profile': profile_errors}, status=status.HTTP_400_BAD_REQUEST)

        travel_states = profile_data.get('travel_states', [])
        if not isinstance(travel_states, list):
            travel_states = []

        # Federation is the eligibility source of truth; home_state stays as the
        # player's residence UF (kept independent so it is never overwritten).
        federation = _resolve_federation(profile_data.get('federation'))

        with transaction.atomic():
            link = account_serializer.save()
            child = link.child
            display_name = (profile_data.get('display_name') or '').strip() or child.full_name or 'Jogador'
            new_profile = PlayerProfile.objects.create(
                user=child,
                display_name=display_name,
                birth_year=profile_data.get('birth_year'),
                gender=profile_data.get('gender', ''),
                home_state=profile_data.get('home_state', 'SP'),
                home_city=profile_data.get('home_city', ''),
                federation=federation,
                travel_states=travel_states,
                competitive_level=profile_data.get('competitive_level', 'amateur'),
                preferred_modality=profile_data.get('preferred_modality', ''),
                is_primary=True,
            )

        from apps.registrations.tasks import match_new_profile_to_entries
        match_new_profile_to_entries.delay(new_profile.pk)

        return Response(
            ParentChildSerializer(link, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

    @viewset_action(detail=False, methods=['post'], url_path='link')
    def link_existing_child(self, request):
        """
        Send a consent invite to an existing player, or finalise an already-accepted invite.

        Accepts { "email": "<existing-user-email>" }.
        - Active link already exists      → return 200.
        - Accepted DependentInvite exists → create ParentChild and return 201.
        - No invite yet                   → create invite + in-app alert, return 202 (requires_invite).
        - Staff accounts bypass the invite requirement.
        """
        email = (request.data.get('email') or '').strip().lower()
        if not email:
            return Response({'detail': 'E-mail obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            child = User.objects.get(email=email, is_active=True)
        except User.DoesNotExist:
            return Response({'detail': 'Nenhum usuário encontrado com esse e-mail.'}, status=status.HTTP_404_NOT_FOUND)

        if child == request.user:
            return Response({'detail': 'Você não pode vincular-se como seu próprio dependente.'}, status=status.HTTP_400_BAD_REQUEST)

        # Already linked — return existing link directly
        existing = ParentChild.objects.filter(parent=request.user, child=child, is_active=True).first()
        if existing:
            return Response(ParentChildSerializer(existing, context={'request': request}).data, status=status.HTTP_200_OK)

        # Plan limit check
        from apps.billing.models import Subscription, Plan
        current_dependents = ParentChild.objects.filter(parent=request.user, is_active=True).count()
        if not request.user.is_staff:
            try:
                sub = request.user.subscription
                if sub.plan.slug == Plan.SLUG_INDIVIDUAL:
                    return Response(
                        {'detail': 'O Plano Individual não permite dependentes. Faça upgrade para o Plano Família.'},
                        status=status.HTTP_403_FORBIDDEN,
                    )
                max_dependents = sub.plan.max_members - 1
                if current_dependents >= max_dependents:
                    return Response(
                        {'detail': f'Limite de {max_dependents} dependente(s) atingido para o seu plano.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except Subscription.DoesNotExist:
                if current_dependents >= 1:
                    return Response(
                        {'detail': 'Você precisa do Plano Família para adicionar mais dependentes.'},
                        status=status.HTTP_403_FORBIDDEN,
                    )

        # Staff bypass: create link directly without requiring an invite
        if request.user.is_staff:
            link, _ = ParentChild.objects.get_or_create(parent=request.user, child=child, defaults={'is_active': True})
            if not link.is_active:
                link.is_active = True
                link.save(update_fields=['is_active'])
            return Response(ParentChildSerializer(link, context={'request': request}).data, status=status.HTTP_201_CREATED)

        # Accepted invite exists — finalise the link
        accepted_invite = DependentInvite.objects.filter(
            parent=request.user, invitee=child, status=DependentInvite.STATUS_ACCEPTED
        ).first()
        if accepted_invite:
            link, _ = ParentChild.objects.get_or_create(parent=request.user, child=child, defaults={'is_active': True})
            if not link.is_active:
                link.is_active = True
                link.save(update_fields=['is_active'])
            logger.info('ParentChild link created via accepted invite: parent=%s child=%s', request.user.id, child.id)
            return Response(ParentChildSerializer(link, context={'request': request}).data, status=status.HTTP_201_CREATED)

        # Pending invite already exists — return it
        pending = DependentInvite.objects.filter(
            parent=request.user, invitee=child, status=DependentInvite.STATUS_PENDING
        ).first()
        if pending:
            return Response(
                {
                    'detail': 'Um convite já foi enviado e aguarda resposta do jogador.',
                    'invite': DependentInviteSerializer(pending, context={'request': request}).data,
                    'requires_invite': True,
                },
                status=status.HTTP_202_ACCEPTED,
            )

        # No invite — create one and notify the invitee
        invite = DependentInvite.objects.create(parent=request.user, invitee=child)
        try:
            from apps.alerts.models import Alert
            parent_name = request.user.full_name or request.user.email
            Alert.objects.get_or_create(
                dedup_key=f'dependent_invite:{invite.id}',
                defaults=dict(
                    user=child,
                    kind=Alert.KIND_OTHER,
                    channel=Alert.CHANNEL_IN_APP,
                    status=Alert.STATUS_SENT,
                    title=f'{parent_name} quer te vincular como dependente',
                    body=(
                        f'{parent_name} ({request.user.email}) enviou um convite para que você '
                        'seja vinculado como dependente na plataforma Tenfy.'
                    ),
                    payload={
                        'action': 'dependent_invite',
                        'invite_id': invite.id,
                        'parent_id': request.user.id,
                        'parent_name': parent_name,
                        'parent_email': request.user.email,
                    },
                ),
            )
        except Exception as exc:
            logger.warning('Could not create invite alert for link endpoint invite=%s: %s', invite.id, exc)

        logger.info('DependentInvite sent via link endpoint: parent=%s invitee=%s', request.user.id, child.id)
        return Response(
            {
                'detail': f'Convite enviado para {child.email}. O vínculo será criado após a aceitação.',
                'invite': DependentInviteSerializer(invite, context={'request': request}).data,
                'requires_invite': True,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @viewset_action(detail=True, methods=['patch'], url_path='update-account')
    def update_child_account(self, request, pk=None):
        """Parent updates child account data (full_name and/or email)."""
        link = self.get_object()
        child = link.child

        full_name = (request.data.get('full_name') or '').strip()
        email = (request.data.get('email') or '').strip().lower()

        if not full_name and not email:
            return Response({'detail': 'Informe ao menos um campo para atualizar.'}, status=status.HTTP_400_BAD_REQUEST)

        if email and User.objects.filter(email=email).exclude(pk=child.pk).exists():
            return Response({'email': 'Este e-mail já está em uso.'}, status=status.HTTP_400_BAD_REQUEST)

        update_fields = []
        if full_name:
            child.full_name = full_name
            update_fields.append('full_name')
        if email:
            child.email = email
            update_fields.append('email')

        child.save(update_fields=update_fields)
        return Response(ParentChildSerializer(link, context={'request': request}).data)

    @viewset_action(detail=True, methods=['delete'], url_path='remove')
    def remove_child(self, request, pk=None):
        """Deactivate the parent-child link. Child account remains active but is no longer managed."""
        link = self.get_object()
        link.is_active = False
        link.save(update_fields=['is_active'])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @viewset_action(detail=True, methods=['post'], url_path='profile')
    def create_profile(self, request, pk=None):
        """Parent creates a sports profile for a specific child."""
        link = self.get_object()
        child = link.child

        from apps.players.models import PlayerProfile
        from apps.players.serializers import PlayerProfileSerializer

        if PlayerProfile.objects.filter(user=child).exists():
            return Response(
                {'detail': 'Este dependente já possui um perfil esportivo.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = PlayerProfileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        profile = PlayerProfile.objects.create(
            user=child,
            display_name=vd.get('display_name') or child.full_name or 'Jogador',
            birth_year=vd.get('birth_year'),
            gender=vd.get('gender', ''),
            home_state=vd.get('home_state', 'SP'),
            home_city=vd.get('home_city', ''),
            federation=vd.get('federation'),
            travel_states=vd.get('travel_states', []),
            competitive_level=vd.get('competitive_level', 'amateur'),
            preferred_modality=vd.get('preferred_modality', ''),
            is_primary=True,
        )
        from apps.registrations.tasks import match_new_profile_to_entries
        match_new_profile_to_entries.delay(profile.pk)
        return Response(PlayerProfileSerializer(profile).data, status=status.HTTP_201_CREATED)

    @viewset_action(detail=True, methods=['post'], url_path='reset-password')
    def reset_password_child(self, request, pk=None):
        """Send password reset email to a child account."""
        link = self.get_object()
        child = link.child

        uid = urlsafe_base64_encode(force_bytes(child.pk))
        token = default_token_generator.make_token(child)
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
        reset_url = f'{frontend_url}/redefinir-senha/{uid}/{token}/'

        from .tasks import send_password_reset_email
        args = (child.id, child.email, child.full_name or '', reset_url)
        try:
            send_password_reset_email.delay(*args)
        except Exception as exc:
            logger.warning('Password reset enqueue failed for child %s: %s', child.id, exc)
            try:
                result = send_password_reset_email.apply(args=args)
                if hasattr(result, 'get'):
                    result.get(propagate=True)
            except Exception as exc2:
                logger.error('Password reset dispatch failed for child %s: %s', child.id, exc2)

        return Response({'detail': f'E-mail de recuperação enviado para {child.email}.'})

    @viewset_action(detail=False, methods=['post'], url_path='request-email-code')
    def request_email_code(self, request):
        """
        Task 10: envia um código de verificação ao e-mail do dependente, ANTES de
        criar a conta. O responsável confirma o código na criação.
        Valida: papel de responsável, formato do e-mail e duplicidade.
        """
        from django.core.validators import validate_email as _validate_email
        from django.core.exceptions import ValidationError as _DjangoValidationError

        if request.user.role != User.ROLE_PARENT:
            return Response(
                {'detail': 'Apenas responsáveis podem cadastrar dependentes.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        email = (request.data.get('email') or '').strip().lower()
        if not email:
            return Response({'email': 'Informe o e-mail do dependente.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            _validate_email(email)
        except _DjangoValidationError:
            return Response(
                {'email': 'Informe um e-mail válido (ex.: nome@dominio.com).'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if User.objects.filter(email=email).exists():
            return Response({'email': 'Este e-mail já possui cadastro.'}, status=status.HTTP_400_BAD_REQUEST)

        if not _send_dependent_email_code(email):
            return Response(
                {'detail': 'Não foi possível enviar o código agora. Tente novamente em instantes.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({'detail': f'Código enviado para {email}.'})

    @viewset_action(detail=False, methods=['get'], url_path='search-players')
    def search_players(self, request):
        """
        Busca jogadores existentes para o responsável escolher quem convidar.

        Busca tolerante (Task 8):
          - ignora acentos e maiúsculas/minúsculas (extensão unaccent);
          - casa por TOKENS (cada palavra como substring, em qualquer ordem) — então
            "silva joao", "joao", "silva" e "joao silva" encontram "João Alves Silva";
          - tolera pequenos erros de digitação via similaridade trigram (pg_trgm),
            ex.: "joao sliva";
          - também procura no e-mail.
        Ordena pelos melhores casamentos primeiro.
        """
        import unicodedata
        from django.db.models import Func, Q
        from django.contrib.postgres.search import TrigramSimilarity

        q = (request.data.get('q') or request.query_params.get('q') or '').strip()
        if len(q) < 2:
            return Response({'detail': 'Digite ao menos 2 caracteres.'}, status=status.HTTP_400_BAD_REQUEST)

        class Unaccent(Func):
            function = 'unaccent'
            arity = 1

        # Dobra a query para ASCII (joão -> joao) para casar com as colunas sem acento.
        q_norm = unicodedata.normalize('NFKD', q).encode('ascii', 'ignore').decode().strip() or q
        tokens = [t for t in q_norm.split() if t]

        # Cada token precisa aparecer no nome (AND) — independente da ordem.
        token_q = Q()
        for t in tokens:
            token_q &= Q(uname__icontains=t)

        _SIM_THRESHOLD = 0.3  # padrão pg_trgm; tolera typos sem virar ruído
        qs = (
            User.objects
            .annotate(
                uname=Unaccent('full_name'),
                uemail=Unaccent('email'),
                sim=TrigramSimilarity(Unaccent('full_name'), q_norm),
            )
            .filter(is_active=True, role=User.ROLE_PLAYER)
            .exclude(pk=request.user.pk)
            .filter(token_q | Q(uemail__icontains=q_norm) | Q(sim__gte=_SIM_THRESHOLD))
            .order_by('-sim', 'full_name')[:20]
        )
        return Response(PlayerSearchSerializer(qs, many=True, context={'request': request}).data)

    @viewset_action(detail=False, methods=['post'], url_path='invite')
    def send_invite(self, request):
        """Send a dependent-link invite to an existing player. Creates an in-app Alert for the invitee."""
        invitee_id = request.data.get('invitee_id')
        if not invitee_id:
            return Response({'detail': 'invitee_id é obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)

        from apps.billing.models import Subscription, Plan
        current_dependents = ParentChild.objects.filter(parent=request.user, is_active=True).count()
        if not request.user.is_staff:
            try:
                sub = request.user.subscription
                if sub.plan.slug == Plan.SLUG_INDIVIDUAL:
                    return Response(
                        {'detail': 'O Plano Individual não permite dependentes. Faça upgrade para o Plano Família.'},
                        status=status.HTTP_403_FORBIDDEN,
                    )
                max_dependents = sub.plan.max_members - 1
                if current_dependents >= max_dependents:
                    return Response(
                        {'detail': f'Limite de {max_dependents} dependente(s) atingido para o seu plano.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except Subscription.DoesNotExist:
                if current_dependents >= 1:
                    return Response(
                        {'detail': 'Você precisa do Plano Família para adicionar mais dependentes.'},
                        status=status.HTTP_403_FORBIDDEN,
                    )

        try:
            invitee = User.objects.get(pk=invitee_id, is_active=True, role=User.ROLE_PLAYER)
        except User.DoesNotExist:
            return Response({'detail': 'Jogador não encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        if invitee == request.user:
            return Response({'detail': 'Você não pode convidar a si mesmo.'}, status=status.HTTP_400_BAD_REQUEST)

        # Block if already an active dependent
        if ParentChild.objects.filter(parent=request.user, child=invitee, is_active=True).exists():
            return Response({'detail': 'Este jogador já é seu dependente.'}, status=status.HTTP_400_BAD_REQUEST)

        # Prevent duplicate pending invites
        existing = DependentInvite.objects.filter(
            parent=request.user, invitee=invitee, status=DependentInvite.STATUS_PENDING
        ).first()
        if existing:
            return Response(
                DependentInviteSerializer(existing, context={'request': request}).data,
                status=status.HTTP_200_OK,
            )

        invite = DependentInvite.objects.create(parent=request.user, invitee=invitee)

        # Create in-app alert for the invitee
        try:
            from apps.alerts.models import Alert
            parent_name = request.user.full_name or request.user.email
            Alert.objects.get_or_create(
                dedup_key=f'dependent_invite:{invite.id}',
                defaults=dict(
                    user=invitee,
                    kind=Alert.KIND_OTHER,
                    channel=Alert.CHANNEL_IN_APP,
                    status=Alert.STATUS_SENT,
                    title=f'{parent_name} quer te vincular como dependente',
                    body=(
                        f'{parent_name} ({request.user.email}) enviou um convite para que você '
                        'seja vinculado como dependente na plataforma Tenfy.'
                    ),
                    payload={
                        'action': 'dependent_invite',
                        'invite_id': invite.id,
                        'parent_id': request.user.id,
                        'parent_name': parent_name,
                        'parent_email': request.user.email,
                    },
                ),
            )
        except Exception as exc:
            logger.warning('Could not create invite alert for invite %s: %s', invite.id, exc)

        logger.info('DependentInvite sent: parent=%s -> invitee=%s invite_id=%s',
                    request.user.id, invitee.id, invite.id)
        return Response(
            DependentInviteSerializer(invite, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

    @viewset_action(detail=False, methods=['get'], url_path='sent-invites')
    def list_sent_invites(self, request):
        """List invites sent by this parent (pending, accepted, declined)."""
        qs = (
            DependentInvite.objects
            .filter(parent=request.user)
            .exclude(status=DependentInvite.STATUS_CANCELED)
            .select_related('invitee')
            .order_by('-created_at')
        )
        return Response(DependentInviteSerializer(qs, many=True, context={'request': request}).data)

    @viewset_action(detail=False, methods=['delete'], url_path=r'sent-invites/(?P<invite_id>[0-9]+)')
    def cancel_invite(self, request, invite_id=None):
        """Cancel a pending invite sent by this parent."""
        try:
            invite = DependentInvite.objects.get(pk=invite_id, parent=request.user, status=DependentInvite.STATUS_PENDING)
        except DependentInvite.DoesNotExist:
            return Response({'detail': 'Convite não encontrado ou já respondido.'}, status=status.HTTP_404_NOT_FOUND)

        invite.status = DependentInvite.STATUS_CANCELED
        invite.save(update_fields=['status'])

        # Remove the alert for the invitee so it disappears from their inbox
        try:
            from apps.alerts.models import Alert
            Alert.objects.filter(dedup_key=f'dependent_invite:{invite.id}').delete()
        except Exception:
            pass

        return Response(status=status.HTTP_204_NO_CONTENT)


class DependentInviteViewSet(viewsets.GenericViewSet):
    """Endpoints for any authenticated user to view and respond to received dependent invites."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DependentInviteSerializer

    def get_queryset(self):
        return (
            DependentInvite.objects
            .filter(invitee=self.request.user)
            .exclude(status__in=[DependentInvite.STATUS_CANCELED])
            .select_related('parent', 'invitee')
            .order_by('-created_at')
        )

    def list(self, request):
        """List received invites."""
        qs = self.get_queryset()
        return Response(DependentInviteSerializer(qs, many=True, context={'request': request}).data)

    @viewset_action(detail=True, methods=['post'], url_path='respond')
    def respond(self, request, pk=None):
        """Accept or decline a received invite. Only the invitee may call this."""
        action = (request.data.get('action') or '').strip()
        if action not in ('accept', 'decline'):
            return Response({'detail': "action deve ser 'accept' ou 'decline'."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            invite = DependentInvite.objects.select_related('parent', 'invitee').get(
                pk=pk, invitee=request.user
            )
        except DependentInvite.DoesNotExist:
            return Response({'detail': 'Convite não encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        if invite.status != DependentInvite.STATUS_PENDING:
            return Response({'detail': 'Este convite já foi respondido ou cancelado.'}, status=status.HTTP_400_BAD_REQUEST)

        if invite.is_expired():
            invite.status = DependentInvite.STATUS_EXPIRED
            invite.save(update_fields=['status'])
            return Response({'detail': 'Este convite expirou. Peça ao responsável que envie um novo convite.'}, status=status.HTTP_400_BAD_REQUEST)

        from django.utils import timezone as tz
        now = tz.now()

        if action == 'accept':
            from apps.billing.models import Subscription, Plan
            # Re-validate plan limit at accept time
            current_dependents = ParentChild.objects.filter(parent=invite.parent, is_active=True).count()
            if not invite.parent.is_staff:
                try:
                    sub = invite.parent.subscription
                    if sub.plan.slug == Plan.SLUG_INDIVIDUAL:
                        return Response(
                            {'detail': 'O responsável não possui Plano Família ativo.'},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    max_dependents = sub.plan.max_members - 1
                    if current_dependents >= max_dependents:
                        return Response(
                            {'detail': 'O responsável atingiu o limite de dependentes do plano.'},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                except Subscription.DoesNotExist:
                    if current_dependents >= 1:
                        return Response(
                            {'detail': 'O responsável não possui Plano Família ativo.'},
                            status=status.HTTP_400_BAD_REQUEST,
                        )

            with transaction.atomic():
                invite.status = DependentInvite.STATUS_ACCEPTED
                invite.responded_at = now
                invite.save(update_fields=['status', 'responded_at'])

                link, _ = ParentChild.objects.get_or_create(
                    parent=invite.parent,
                    child=invite.invitee,
                    defaults={'is_active': True},
                )
                if not link.is_active:
                    link.is_active = True
                    link.save(update_fields=['is_active'])

            # Remove the invite alert — it's no longer actionable
            try:
                from apps.alerts.models import Alert
                Alert.objects.filter(dedup_key=f'dependent_invite:{invite.id}').delete()
            except Exception:
                pass

            logger.info('DependentInvite accepted: invite=%s parent=%s child=%s', invite.id, invite.parent.id, invite.invitee.id)
            return Response({'detail': 'Convite aceito. Você agora é dependente do responsável.', 'link_id': link.id})

        else:  # decline
            with transaction.atomic():
                invite.status = DependentInvite.STATUS_DECLINED
                invite.responded_at = now
                invite.save(update_fields=['status', 'responded_at'])

            # Remove the invite alert from the invitee's inbox
            try:
                from apps.alerts.models import Alert
                Alert.objects.filter(dedup_key=f'dependent_invite:{invite.id}').delete()
            except Exception:
                pass

            # Notify the parent that the invite was declined
            try:
                from apps.alerts.models import Alert
                invitee_name = invite.invitee.full_name or invite.invitee.email
                Alert.objects.get_or_create(
                    dedup_key=f'invite_declined:{invite.id}',
                    defaults=dict(
                        user=invite.parent,
                        kind=Alert.KIND_OTHER,
                        channel=Alert.CHANNEL_IN_APP,
                        status=Alert.STATUS_SENT,
                        title=f'Convite recusado',
                        body=(
                            f'{invitee_name} recusou seu convite de vínculo familiar. '
                            'Você pode enviar um novo convite a qualquer momento.'
                        ),
                        payload={
                            'action': 'invite_declined',
                            'invite_id': invite.id,
                            'invitee_name': invitee_name,
                            'invitee_email': invite.invitee.email,
                        },
                    ),
                )
            except Exception as exc:
                logger.warning('Could not create decline alert for parent invite=%s: %s', invite.id, exc)

            logger.info('DependentInvite declined: invite=%s', invite.id)
            return Response({'detail': 'Convite recusado.'})


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def data_export(request):
    """
    LGPD RF-026: Returns a JSON snapshot of all personal data for the authenticated user.
    Covers user record, player profiles, watchlist items, tournament results and alerts.
    """
    from apps.players.models import PlayerProfile
    from apps.watchlist.models import WatchlistItem, TournamentResult
    from apps.alerts.models import Alert

    user = request.user

    profiles = list(
        PlayerProfile.objects.filter(user=user).values(
            'id', 'display_name', 'birth_year', 'birth_date', 'gender',
            'home_state', 'home_city', 'travel_radius_km', 'travel_states', 'competitive_level',
            'dominant_hand', 'is_primary', 'external_ids',
            'created_at', 'updated_at',
        )
    )
    profile_ids = [p['id'] for p in profiles]

    watchlist = list(
        WatchlistItem.objects.filter(user=user).select_related('edition__tournament').values(
            'id', 'edition__id', 'edition__title', 'edition__start_date', 'edition__end_date',
            'user_status', 'alert_on_deadline', 'alert_on_changes', 'alert_on_draws',
            'created_at', 'updated_at',
        )
    )

    results = list(
        TournamentResult.objects.filter(watchlist_item__user=user).values(
            'id', 'watchlist_item_id', 'category_played', 'position', 'wins', 'losses',
            'notes', 'created_at',
        )
    )

    alerts = list(
        Alert.objects.filter(user=user).values(
            'id', 'kind', 'channel', 'status', 'title', 'dispatched_at', 'read_at', 'created_at',
        )
    )

    payload = {
        'exported_at': timezone.now().isoformat(),
        'user': {
            'id': user.id,
            'email': user.email,
            'full_name': user.full_name,
            'phone': user.phone,
            'role': user.role,
            'email_verified': user.email_verified,
            'marketing_consent': user.marketing_consent,
            'consent_version': user.consent_version,
            'consented_at': user.consented_at.isoformat() if user.consented_at else None,
            'date_joined': user.date_joined.isoformat() if hasattr(user, 'date_joined') and user.date_joined else None,
            'last_login': user.last_login.isoformat() if user.last_login else None,
        },
        'player_profiles': profiles,
        'watchlist': watchlist,
        'tournament_results': results,
        'alerts': alerts,
    }

    response = JsonResponse(payload, json_dumps_params={'ensure_ascii': False, 'indent': 2})
    response['Content-Disposition'] = f'attachment; filename="tenfy_data_{user.id}.json"'
    return response


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def password_reset_confirm(request):
    """Confirma redefinição de senha com uid + token."""
    uid = request.data.get('uid', '')
    token = request.data.get('token', '')
    new_password = request.data.get('new_password', '')
    confirm_password = request.data.get('confirm_password', '')

    if not all([uid, token, new_password, confirm_password]):
        return Response({'detail': 'Todos os campos são obrigatórios.'}, status=status.HTTP_400_BAD_REQUEST)

    if new_password != confirm_password:
        return Response({'detail': 'As senhas não coincidem.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user_pk = force_str(urlsafe_base64_decode(uid))
        user = User.objects.get(pk=user_pk, is_active=True)
    except (User.DoesNotExist, ValueError, TypeError):
        return Response({'detail': 'Link inválido ou expirado.'}, status=status.HTTP_400_BAD_REQUEST)

    if not default_token_generator.check_token(user, token):
        return Response({'detail': 'Link inválido ou expirado.'}, status=status.HTTP_400_BAD_REQUEST)

    # Validate password against AUTH_PASSWORD_VALIDATORS
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError as DjValidationError
    try:
        validate_password(new_password, user)
    except DjValidationError as exc:
        return Response(
            {'detail': exc.messages[0] if exc.messages else 'Senha não atende aos requisitos.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user.set_password(new_password)
    user.save()
    return Response({'detail': 'Senha redefinida com sucesso.'})
