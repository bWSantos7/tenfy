"""Autenticação JWT silenciosa (padrão global do projeto).

Um token expirado/inválido NÃO deve retornar 401 por si só — deve ser tratado
como requisição anônima, deixando a CAMADA DE PERMISSÃO decidir:
  - endpoints públicos (AllowAny): funcionam normalmente (ex.: /register, /login,
    /billing/plans) mesmo quando o frontend manda um token velho no header;
  - endpoints protegidos (IsAuthenticated): retornam 401 via permissão, e o
    interceptor do frontend faz o refresh e re-tenta.

Sem isso, o JWTAuthentication padrão levanta AuthenticationFailed (401) ao ver um
token expirado no header ANTES de checar a permissão, quebrando o fluxo público
de cadastro/login para quem tem um token antigo no navegador.
"""
from rest_framework_simplejwt.authentication import JWTAuthentication


class SilentJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        try:
            return super().authenticate(request)
        except Exception:
            # Token ausente/expirado/malformado → anônimo (não 401 aqui).
            return None
