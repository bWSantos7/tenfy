"""
Handoff de sessão app <-> web.

Motivação: na App Store, vender assinatura digital por gateway externo dentro do app
aciona a regra de In-App Purchase (Apple 3.1.1). Por isso o app iOS opera só com login e
o cadastro/assinatura acontecem no site (Safari). Como o login é por JWT em armazenamento
local, a sessão criada no Safari não existe dentro da WebView do app.

Este módulo resolve o "retorno automático logado": o site, após o usuário assinar, gera um
token de uso único (curta duração) e monta um universal link. Ao abrir o app, a WebView
carrega `/app/continuar?ht=<token>`, que troca o token por um par JWT — entrando logado sem
o usuário digitar a senha de novo.

Segurança:
- token aleatório (`secrets.token_urlsafe`), sem PII;
- guardado só no cache, com TTL curto;
- uso único (removido do cache ao trocar);
- endpoints com throttle; a troca nunca revela se o e-mail existe.
"""
import logging
import secrets

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import UserSerializer

logger = logging.getLogger('apps.accounts')

User = get_user_model()

# Prefixo da chave de cache e validade do token de handoff.
_CACHE_PREFIX = 'app_handoff:'
_TTL_SECONDS = 300  # 5 minutos — tempo suficiente para o redirecionamento, curto o bastante.


def _cache_key(token: str) -> str:
    return f'{_CACHE_PREFIX}{token}'


# Throttles com escopo fixo (FBVs não expõem `throttle_scope`, então ScopedRateThrottle
# não se aplica aqui): UserRateThrottle/AnonRateThrottle usam o `scope` da subclasse para
# ler a taxa em DEFAULT_THROTTLE_RATES e compor a chave de cache.
class _MintThrottle(UserRateThrottle):
    scope = 'app_handoff'


class _ExchangeThrottle(AnonRateThrottle):
    scope = 'app_handoff_exchange'


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@throttle_classes([_MintThrottle])
def app_handoff_start(request):
    """Gera um token de uso único para o usuário autenticado (chamado no site/Safari)."""
    token = secrets.token_urlsafe(32)
    cache.set(_cache_key(token), request.user.id, timeout=_TTL_SECONDS)
    logger.info('app_handoff: token gerado para user %s', request.user.id)
    return Response({'token': token, 'expires_in': _TTL_SECONDS})


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
@throttle_classes([_ExchangeThrottle])
def app_handoff_exchange(request):
    """Troca o token de uso único por um par JWT (chamado dentro da WebView do app)."""
    token = str(request.data.get('token', '')).strip()
    if not token:
        return Response({'detail': 'Token ausente.'}, status=status.HTTP_400_BAD_REQUEST)

    key = _cache_key(token)
    user_id = cache.get(key)
    # Uso único atômico: o delete é a "reivindicação" do token. Em duas requisições
    # concorrentes com o mesmo token, só uma recebe delete=True (DEL é atômico no Redis);
    # as demais são rejeitadas. Evita que um link gere duas sessões.
    if not user_id or not cache.delete(key):
        return Response(
            {'detail': 'Link expirado ou já utilizado. Faça login novamente.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        return Response(
            {'detail': 'Não foi possível continuar. Faça login novamente.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    refresh = RefreshToken.for_user(user)
    logger.info('app_handoff: sessão entregue ao app para user %s', user.id)
    return Response({
        'user': UserSerializer(user, context={'request': request}).data,
        'access': str(refresh.access_token),
        'refresh': str(refresh),
    })
