# Universal Links / App Links — retorno automático ao app

Permite que, após o usuário criar conta e assinar **no site** (Safari/Chrome), ele volte
ao app **já logado**, sem digitar a senha de novo. É a peça que viabiliza o modelo "login
apenas" no iOS (conformidade Apple 3.1.1): cadastro e pagamento ficam fora do app.

## Como funciona

1. No site, ao confirmar o pagamento, o frontend chama `POST /api/auth/app-handoff/`
   (autenticado) e recebe um token de uso único (TTL 5 min).
2. O frontend monta um universal link: `https://tenfy.com.br/app/continuar?ht=<token>`.
3. O usuário toca em "Abrir no app Tenfy". O iOS/Android abre o app (se instalado) nessa URL.
4. A WebView do app carrega `/app/continuar`, que chama
   `POST /api/auth/app-handoff/exchange/` e troca o token por uma sessão JWT → entra logado.
5. Se o app não estiver instalado, o link cai no navegador e a troca acontece na web —
   sem beco sem saída.

## Arquivos de associação (servidos pelo frontend)

- `frontend/public/.well-known/apple-app-site-association` (iOS)
- `frontend/public/.well-known/assetlinks.json` (Android)

Ambos têm **placeholders** que precisam ser preenchidos quando as contas existirem:

| Placeholder | Onde obter |
|---|---|
| `REPLACE_WITH_APPLE_TEAM_ID` | Apple Developer → Membership → Team ID (10 caracteres) |
| `REPLACE_WITH_PLAY_APP_SIGNING_SHA256_FINGERPRINT` | Play Console → App signing → SHA-256, ou `eas credentials` |

## Requisitos de hosting (atenção no deploy)

O domínio `https://tenfy.com.br` precisa servir:

- `GET /.well-known/apple-app-site-association`
  - **Content-Type**: `application/json` (sem extensão no arquivo)
  - **HTTPS**, status 200, **sem redirect**
- `GET /.well-known/assetlinks.json` (Content-Type `application/json`)

> ⚠️ Servidores estáticos (ex.: `serve -s dist`) podem **não servir arquivos/pastas
> iniciados por ponto** (`.well-known`) por padrão. Validar após o deploy:
> `curl -i https://tenfy.com.br/.well-known/apple-app-site-association`
> Se vier 404, ajustar o servidor/host para expor `.well-known`.

## Config do app (já feita)

- `mobile/app.json` → `ios.associatedDomains: ["applinks:tenfy.com.br"]`
- `mobile/app.json` → `android.intentFilters` com `autoVerify` para `https://tenfy.com.br/app/*`
- `mobile/src/WebAppShell.tsx` → carrega o deep link na WebView (cold e warm start)

## Backend

- `backend/apps/accounts/app_handoff.py` — geração e troca do token (cache, uso único)
- Rotas: `/api/auth/app-handoff/` e `/api/auth/app-handoff/exchange/`
