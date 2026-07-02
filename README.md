# Tenfy

**Tenfy** é uma plataforma centrada no jogador para agregar torneios de tênis no Brasil, consolidando calendário, regras de inscrição, categorias, elegibilidade, listas de inscritos, rankings e alertas em um único ecossistema.

O projeto é composto por backend Django, frontend web, aplicativo mobile (casca nativa Expo que carrega o app web dentro de uma WebView), PostgreSQL, Redis/Celery, integrações de pagamento, notificações, pipelines de ingestão e automações externas via n8n.

---

## Sumário

- [Visão geral](#visão-geral)
- [Status atual](#status-atual)
- [Arquitetura](#arquitetura)
- [Stack técnica](#stack-técnica)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Integrações de dados](#integrações-de-dados)
- [Automações n8n](#automações-n8n)
- [Desenvolvimento local](#desenvolvimento-local)
- [Variáveis de ambiente](#variáveis-de-ambiente)
- [Testes](#testes)
- [Deploy em produção](#deploy-em-produção)
- [Build mobile](#build-mobile)
- [Segurança](#segurança)
- [Contribuição e fluxo de trabalho](#contribuição-e-fluxo-de-trabalho)
- [Licença](#licença)

---

## Visão geral

O Tenfy resolve a fragmentação do ecossistema de torneios de tênis. Hoje, jogadores, pais e treinadores precisam consultar múltiplos sites de confederações, federações estaduais, plataformas de inscrição e regulamentos em PDF para descobrir:

- quais torneios estão abertos;
- quais categorias existem;
- quais categorias são compatíveis com o perfil do jogador;
- quais prazos estão próximos;
- quais atletas estão inscritos;
- qual o ranking/posição dos inscritos quando a fonte fornece esse dado;
- qual é o link oficial de inscrição;
- quais dados foram alterados desde a última sincronização.

A proposta do app é ser uma camada de inteligência e organização, sem substituir a fonte oficial. Sempre que possível, o sistema mantém `source_url`, `source_name`, `synced_at`, `confidence` e histórico de alterações.

---

## Status atual

### Funcionalidades principais

- Cadastro, login, recuperação de senha e verificação de e-mail.
- Perfil de jogador e preferências.
- Catálogo de torneios.
- Página de torneio com fonte oficial, datas, categorias, status e lista de inscritos.
- Watchlist e alertas.
- Painel administrativo.
- Integrações com fontes externas.
- Importação de inscrições por fonte.
- Pipeline de qualidade com `dry_run`, `quality_gate`, warnings e errors.
- App mobile como casca WebView (Expo) que carrega o app web.
- Projeto iOS nativo pronto para build via EAS (sem Mac) ou Xcode; publicação depende apenas da conta Apple Developer.
- Backend Django REST API em produção.
- Deploy no Railway.

### Fontes de inscrições

> Hoje todas as fontes são normalizadas pelo **`tournament-extractor`** (caminho único).
> A tabela abaixo descreve a origem/maturidade por fonte; os fluxos n8n/Mongo citados
> são fallback desligado (ver [Integrações de dados](#integrações-de-dados)).

| Fonte | Status |
|---|---|
| CBT / Tênis Integrado | Automação validada. Coleta inscritos, categorias, ranking/posição quando disponível e status financeiro. |
| FBT | Suporte de backend/parser adicionado. Deve ser validado em fluxo seguro antes de importação real. |
| FPT | Torneios podem ser catalogados, mas listas nominais podem exigir login ou não estar disponíveis publicamente. |
| COSAT/COSANT | Consumo planejado via MongoDB exclusivo do scraper COSAT, sincronizando para PostgreSQL oficial. |
| Manual/Admin | Permitido como fallback operacional, com rastreabilidade. |

---

## Arquitetura

```text
┌──────────────────────────────────────────────────────────────┐
│                  Aplicativo Mobile (Expo)                    │
│        WebView que carrega o app web (frontend)              │
└──────────────────────────────┬───────────────────────────────┘
                               │ carrega o app web · HTTPS / REST
┌──────────────────────────────▼───────────────────────────────┐
│                     Backend Django REST                       │
│       Django · DRF · Celery · PostgreSQL · Redis              │
│                                                              │
│  ┌─────────────────┐ ┌────────────────┐ ┌─────────────────┐ │
│  │ Ingestão/Dados  │ │ Assinaturas    │ │ Elegibilidade   │ │
│  │ Fontes externas │ │ Asaas          │ │ Categorias      │ │
│  └─────────────────┘ └────────────────┘ └─────────────────┘ │
└──────────────────────────────┬───────────────────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
     PostgreSQL              Redis              Cloudinary
  Banco oficial        Fila/cache Celery       Mídia/avatars

          ┌────────────────────┐
          │ n8n / Workflows    │
          │ CBT, FBT, fontes   │
          └────────────────────┘

          ┌────────────────────┐
          │ Mongo COSAT        │
          │ Somente scraper    │
          └────────────────────┘
```

### Princípios

- PostgreSQL é o banco oficial do produto.
- MongoDB COSAT é fonte intermediária exclusiva do scraper COSAT.
- O backend principal não deve fazer scraping COSAT diretamente.
- Frontend/mobile nunca devem conter segredos ou regras críticas.
- Qualquer importação externa deve passar por validação, `dry_run` e `quality_gate`.
- Dados externos devem preservar origem e confiança.

---

## Stack técnica

### Backend

| Camada | Tecnologia |
|---|---|
| Framework | Django + Django REST Framework |
| Banco oficial | PostgreSQL |
| Cache/fila | Redis |
| Jobs | Celery + Celery Beat |
| Autenticação | JWT / SimpleJWT |
| E-mail | Resend |
| Mídia | Cloudinary |
| Pagamentos | Asaas |
| Observabilidade | Sentry |
| Servidor | Gunicorn |

### Mobile

O app mobile é uma casca nativa Expo que renderiza o app web dentro de uma WebView — a experiência é o próprio frontend web, garantindo paridade total. Toda a lógica (auth, navegação, dados) vive no web; o app trata apenas do chrome nativo, loading e erro de conexão.

| Camada | Tecnologia |
|---|---|
| Runtime | Expo / React Native |
| Renderização | WebView (`react-native-webview`) carregando o app web |
| Linguagem | TypeScript |
| Build | EAS Build |

### Infraestrutura

| Serviço | Uso |
|---|---|
| Railway | Deploy backend, frontend, worker, Redis, Postgres e serviços auxiliares |
| PostgreSQL | Banco oficial |
| Redis | Broker/cache |
| n8n | Workflows de sincronização |
| MongoDB | Banco intermediário exclusivo do scraper COSAT |
| GitHub | Versionamento |
| Resend | E-mails transacionais |
| Cloudinary | Imagens |
| Sentry | Erros em produção |

---

## Estrutura do projeto

```text
tenfy/
├── backend/
│   ├── apps/
│   │   ├── accounts/        # usuários, autenticação, OTP, LGPD
│   │   ├── alerts/          # alertas, notificações e preferências
│   │   ├── admin_panel/     # APIs do painel administrativo
│   │   ├── audit/           # logs e auditoria
│   │   ├── billing/         # planos, assinaturas, Asaas e webhooks
│   │   ├── eligibility/     # motor de compatibilidade/elegibilidade
│   │   ├── ingestion/       # conectores e pipeline de ingestão
│   │   ├── marketplace/     # base futura de marketplace
│   │   ├── players/         # perfis de jogadores
│   │   ├── registrations/   # listas de inscritos e integrações de federações
│   │   ├── sources/         # cadastro de fontes
│   │   ├── tournaments/     # torneios e edições
│   │   └── watchlist/       # favoritos/watchlist
│   ├── config/
│   ├── requirements.txt
│   ├── railway.json
│   └── railway.worker.json
│
├── frontend/
│   └── ...
│
├── mobile/
│   ├── src/              # casca WebView, deep-link, push
│   ├── ios/              # projeto Xcode nativo (gerado via expo prebuild)
│   ├── app.json
│   └── eas.json
│
├── docs/
│   └── mobile/           # build/entrega iOS e metadados App Store
├── CLAUDE.md
└── README.md
```

---

## Integrações de dados

> **Estado atual (2026):** a ingestão de torneios/inscritos vem **100% do
> `tournament-extractor`** (serviço externo que grava no schema `extractor` do
> mesmo Postgres; o backend sincroniza via `sync_from_extractor`). Os caminhos
> descritos abaixo — **Mongo COSAT/ITF**, conectores in-backend e **workflows
> n8n de inscritos** — estão **desligados** e permanecem apenas como **fallback
> manual** (flags `*_MONGO_ENABLED=False`; agendamentos em `OBSOLETE_TASKS`).
> A subseção CBT via n8n abaixo reflete o histórico, não o fluxo ativo.

### CBT / Tênis Integrado

A CBT/Tênis Integrado é a integração mais madura. O fluxo validado coleta:

- nome do atleta;
- categoria;
- identificador externo do atleta;
- ranking/posição quando disponível;
- status financeiro/pagamento quando disponível;
- fonte;
- confiança;
- timestamp de sincronização.

Fluxo esperado:

```text
n8n
→ federation-sync-targets?source=cbt
→ parse-entries
→ quality_gate
→ import dry_run=true
→ quality_gate
→ import dry_run=false
→ PostgreSQL
```

### FBT

O backend reconhece `source=fbt` e possui parser dedicado. O fluxo deve ser testado inicialmente em modo seguro:

```text
Manual Trigger
→ source=fbt
→ parse
→ dry_run=true
→ sem salvar dados reais
```

A importação real deve ser ativada somente após validação de entries reais, `errors=[]` e `quality_gate.can_save=true`.

### FPT

A fonte FPT pode exigir login para algumas listas nominais de inscritos. Quando não houver lista pública acessível, o sistema deve registrar limitação/pendência e não inventar dados.

### COSAT/COSANT

O scraper COSAT roda separadamente e grava dados em um MongoDB dedicado. O Tenfy deve consumir esse Mongo como fonte intermediária e sincronizar os dados normalizados para o PostgreSQL oficial.

Diretriz:

```text
scraper COSAT
→ Mongo COSAT
→ backend Django sync_cosat_from_mongo
→ PostgreSQL
→ app/API
```

---

## Automações n8n

### Workflow CBT

Workflow recomendado:

```text
Sync CBT Inscritos
```

Configuração esperada:

```text
source=cbt
needs_sync=true
limit=50
Cron: a cada 1 hora
SALVAR dry_run=false: ativo somente após validação
Quality gates: obrigatórios
```

O workflow deve processar somente CBT. FPT, COSAT, FBT ou fontes genéricas devem ficar em workflows separados.

### Workflow FBT

Workflow recomendado:

```text
Sync FBT Inscritos
```

Configuração inicial:

```text
source=fbt
needs_sync=true
limit=50
Cron: desativado inicialmente
SALVAR dry_run=false: desativado inicialmente
Execução: Manual Trigger
```

### Boas práticas n8n

- Nunca inserir token hardcoded em nodes.
- Usar variável global `TENNIS_IMPORT_TOKEN`.
- Enviar token somente no header `X-Import-Token`.
- Nunca salvar se `parser_warning=true`.
- Nunca salvar se `quality_gate.can_save=false`.
- Nunca salvar se `entries_count=0`.
- Nunca salvar se `errors.length > 0`.
- Manter FBT/FPT/COSAT separados até cada fonte estar validada.

---

## Desenvolvimento local

### Pré-requisitos

- Python 3.11+
- Node.js 20+ (Expo SDK 54 exige 20.19+)
- PostgreSQL 14+
- Redis 7+
- Git

### Backend

```bash
cd backend

python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt

python manage.py migrate
python manage.py seed_plans
python manage.py seed_sources
python manage.py runserver
```

### Worker/Celery

```bash
cd backend
celery -A config worker --loglevel=info
```

### Beat

```bash
cd backend
celery -A config beat --loglevel=info
```

### Mobile

```bash
cd mobile
npm install
npx expo start
```

> O app abre uma WebView apontando para `EXPO_PUBLIC_WEB_URL` (padrão `https://tenfy.com.br`). Não há telas nativas a desenvolver — ajustes de UI são feitos no `frontend/`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

---

## Variáveis de ambiente

Nunca commitar valores reais. Use apenas `.env` local e variáveis do Railway.

### Backend

```env
SECRET_KEY=
DEBUG=False
ALLOWED_HOSTS=api.tenfy.com.br,tenfy.com.br,healthcheck.railway.app
DATABASE_URL=
REDIS_URL=
FRONTEND_URL=https://tenfy.com.br
CORS_ALLOWED_ORIGINS=https://tenfy.com.br
CSRF_TRUSTED_ORIGINS=https://tenfy.com.br,https://api.tenfy.com.br

RESEND_API_KEY=
DEFAULT_FROM_EMAIL=no-reply@tenfy.com.br
RESEND_FROM_EMAIL=no-reply@tenfy.com.br

CLOUDINARY_URL=

VAPID_PRIVATE_KEY=
VAPID_PUBLIC_KEY=
VAPID_CLAIMS_EMAIL=no-reply@tenfy.com.br

ASAAS_API_KEY=
ASAAS_ENVIRONMENT=sandbox
ASAAS_WEBHOOK_TOKEN=

SENTRY_DSN=
SENTRY_ENVIRONMENT=production

IMPORT_API_TOKEN=
```

### COSAT Mongo

```env
COSAT_MONGO_ENABLED=true
COSAT_MONGO_URL=
COSAT_MONGO_DB=
COSAT_MONGO_COLLECTION_TOURNAMENTS=
COSAT_MONGO_COLLECTION_ENTRIES=
COSAT_MONGO_COLLECTION_RANKINGS=
COSAT_MONGO_CONNECT_TIMEOUT_MS=5000
```

### Frontend/mobile

```env
# Frontend web
VITE_API_BASE_URL=https://api.tenfy.com.br

# Mobile (WebView): URL do app web que o app carrega
EXPO_PUBLIC_WEB_URL=https://tenfy.com.br
```

---

## Testes

```bash
cd backend
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --keepdb
```

Testes direcionados:

```bash
python manage.py test apps.registrations
python manage.py test apps.ingestion
python manage.py test apps.billing
python manage.py test apps.accounts
python manage.py test apps.eligibility
python manage.py test apps.players
python manage.py test apps.tournaments
python manage.py test apps.admin_panel
python manage.py test apps.alerts
```

Mobile (TypeScript):

```bash
cd mobile
npx tsc --noEmit
```

Frontend (TypeScript + build):

```bash
cd frontend
node_modules/.bin/tsc --noEmit
npm run build
```

> **Nota:** `python manage.py test` requer Python 3.11+ e PostgreSQL configurados.
> Em ambiente Windows sem Python no PATH, use WSL, Railway CLI (`railway run`) ou CI/CD.

---

## Deploy em produção

Produção no Railway com serviços separados:

- backend;
- worker/beat;
- frontend;
- PostgreSQL;
- Redis;
- serviços auxiliares, como Mongo COSAT e crawler COSAT.

Fluxo padrão:

```text
push para master
→ Railway detecta alteração
→ build
→ migrate
→ start backend/worker/frontend
```

Antes de deploy:

```bash
git status
git diff --stat
python manage.py check
python manage.py makemigrations --check --dry-run
```

Após deploy:

```bash
curl https://api.tenfy.com.br/health/
```

---

## Build mobile

O app mobile builda pela nuvem via **EAS Build** — **não precisa de Mac, nem para iOS**. Os comandos são disparados do Windows/Linux.

### Scripts (em `mobile/`)

```bash
# Android
npm run build:android:preview   # APK interno para teste
npm run build:android:prod      # AAB de produção

# iOS
npm run build:ios:sim           # build de Simulador (NÃO exige conta Apple)
npm run build:ios:preview       # build interno (device)
npm run build:ios:prod          # build de produção
npm run submit:ios              # envia para App Store Connect / TestFlight
```

### Projeto nativo iOS (Xcode)

A pasta `mobile/ios/` (projeto Xcode nativo) é versionada, gerada via `expo prebuild`. Serve tanto para o build no EAS quanto para entrega a quem compila localmente no Xcode.

> ⚠️ `mobile/ios/` é código gerado a partir de `mobile/app.json`. Rodar `npx expo prebuild -p ios --clean` regenera a pasta e sobrescreve edições manuais no nativo.

### Documentação iOS

| Doc | Para quê |
|---|---|
| `docs/mobile/ios-eas-build.md` | Buildar/publicar iOS via EAS, sem Mac (recomendado) |
| `docs/mobile/ios-xcode-handoff.md` | Entregar o `ios/` para compilar no Xcode (Mac) |
| `docs/mobile/app-store-metadata.md` | Textos prontos para o App Store Connect |

### Custo

- **EAS Build:** plano Free (15 builds iOS/mês) = **US$ 0**.
- **Apple Developer Program:** **US$ 99/ano** — obrigatório para build em device, TestFlight e App Store.
- **Push (Expo):** grátis.

---

## Segurança

### Regras obrigatórias

- Nunca commitar `.env`.
- Nunca commitar exports do n8n contendo tokens.
- Nunca colocar `IMPORT_API_TOKEN` no frontend/mobile.
- Nunca colocar chaves Railway, Resend, Cloudinary, Asaas, Sentry, Redis, Postgres ou Mongo em arquivos versionados.
- Toda chave exposta deve ser rotacionada.
- Usar `git add` seletivo.
- Conferir `git status` antes de todo commit.
- Manter `ALLOWED_HOSTS`, CORS e CSRF restritos.
- Não usar SQLite em produção.
- Não deixar `DEBUG=True` em produção.
- Não executar importação real sem `dry_run` e `quality_gate`.

### Arquivos locais ignorados

O `.gitignore` deve cobrir:

- `.env*`;
- `.venv/`;
- `node_modules/`;
- exports n8n;
- arquivos temporários;
- caches;
- logs;
- snapshots locais.

---

## Contribuição e fluxo de trabalho

### Antes de alterar código

Ler:

```text
CLAUDE.md
```

### Fluxo recomendado

```text
1. Criar/editar código.
2. Rodar testes/checks.
3. Revisar diff.
4. Fazer git add seletivo.
5. Commit.
6. Push.
7. Validar Railway.
8. Validar /health/.
9. Validar endpoint afetado.
```

### Commits sugeridos

```bash
git add <arquivos específicos>
git commit -m "feat: add FBT source detection and parser"
git push origin master
```

Evitar:

```bash
git add .
```

salvo quando o diff inteiro tiver sido auditado.

---

## Licença

Projeto privado. Todos os direitos reservados.
