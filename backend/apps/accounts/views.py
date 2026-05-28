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
)
from .models import CoachAthlete, ParentChild

logger = logging.getLogger('apps.accounts')

User = get_user_model()


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
            email = request.data.get('email')
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
        # Invalidate all JWT tokens
        try:
            from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
            OutstandingToken.objects.filter(user=user).update(token='')
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
        # Enforce role check — only parent/responsible accounts can add dependents
        if request.user.role != 'parent':
            return Response(
                {'detail': 'Apenas contas do tipo Responsável/Pai podem cadastrar dependentes.'},
                status=status.HTTP_403_FORBIDDEN,
            )

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
                travel_states=travel_states,
                competitive_level=profile_data.get('competitive_level', 'amateur'),
                tennis_class=profile_data.get('tennis_class', ''),
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
        Link an *existing* user account as a child/dependent.
        Accepts { "email": "<existing-user-email>" }.
        Used when the child already has a Tenfy account and the parent
        wants to manage it under the Família plan.
        """
        email = (request.data.get('email') or '').strip().lower()
        if not email:
            return Response({'detail': 'E-mail obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)

        # Plan limit check — same rules as create / create_with_profile
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

        try:
            child = User.objects.get(email=email, is_active=True)
        except User.DoesNotExist:
            return Response(
                {'detail': 'Nenhum usuário encontrado com esse e-mail.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if child == request.user:
            return Response(
                {'detail': 'Você não pode vincular-se como seu próprio dependente.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # If the link already exists and is active, return it directly
        existing = ParentChild.objects.filter(parent=request.user, child=child).first()
        if existing:
            if existing.is_active:
                return Response(
                    ParentChildSerializer(existing, context={'request': request}).data,
                    status=status.HTTP_200_OK,
                )
            # Re-activate a previously deactivated link
            existing.is_active = True
            existing.save(update_fields=['is_active'])
            return Response(
                ParentChildSerializer(existing, context={'request': request}).data,
                status=status.HTTP_200_OK,
            )

        link = ParentChild.objects.create(parent=request.user, child=child)
        logger.info(
            'ParentChild link created: parent=%s -> child=%s (existing account)',
            request.user.id, child.id,
        )
        return Response(
            ParentChildSerializer(link, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
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
            travel_states=vd.get('travel_states', []),
            competitive_level=vd.get('competitive_level', 'amateur'),
            tennis_class=vd.get('tennis_class', ''),
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
            'dominant_hand', 'tennis_class', 'is_primary', 'external_ids',
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
