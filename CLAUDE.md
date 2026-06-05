# CLAUDE.md - Guia obrigatorio para IA no Tenfy

Atualizado em 2026-06-04.

Este arquivo deve ser lido antes de qualquer alteracao no projeto. Ele existe para reduzir retrabalho, evitar decisoes perigosas em producao e manter todos os agentes alinhados com o produto real que esta no repositorio.

## 1. Leitura rapida obrigatoria

- Tenfy e uma plataforma para jogadores, pais/responsaveis e treinadores acompanharem torneios de tenis, categorias, elegibilidade, agenda, inscricoes publicadas por federacoes, resultados, alertas e assinaturas.
- O backend Django e a fonte da verdade para regras de negocio, permisssoes, pagamentos, dados externos normalizados e integracoes.
- PostgreSQL e o banco oficial do produto. MongoDB e intermediario apenas para dados vindos de scrapers externos.
- Frontend web e mobile Expo consomem a API. Eles nao podem conter segredos nem regras criticas.
- Os arquivos `Sync CBT Inscritos.json`, `Sync FBT Inscritos.json` e `Sync FPT (SP) Inscritos.json` sao exports de workflows que rodam no n8n. Nao sao scripts locais do app.
- Scraping COSAT/ITF nao pertence a este repositorio principal. O scraper roda em outro repositorio/servico e grava no MongoDB. O backend apenas sincroniza MongoDB -> PostgreSQL.
- Nunca inventar torneios, atletas, ranking, pagamento, inscricao, status, cidade, data, categoria ou criterio de elegibilidade.
- Nunca commitar secrets, `.env`, tokens n8n, credenciais Railway, chaves Asaas, Resend, Cloudinary, Sentry, Redis, Postgres ou Mongo.
- Antes de `dry_run=false`, deploy, migration, push ou mudanca de producao, confirmar risco e autorizacao do usuario quando houver impacto real.

## 2. Produto e escopo

O MVP contratual cobre:

- calendario/listagem consolidada de torneios;
- perfil esportivo do jogador;
- analise basica de compatibilidade/elegibilidade por perfil, idade, categoria, localidade e modalidade quando houver dados;
- planos e assinaturas via Asaas;
- painel administrativo minimo para fontes, torneios, revisao e operacao;
- rastreabilidade da origem dos dados.

Produto expandido ja existe no codigo e deve ser preservado:

- app mobile Expo/React Native;
- watchlist/agenda;
- alertas in-app, push e preferencias;
- listas de inscritos publicadas por federacoes;
- auto-discovery de inscricoes por `FederationEntry` -> `TournamentRegistration`;
- resultados;
- responsavel/dependentes, convites e familia;
- treinador/alunos;
- painel admin mais amplo;
- workflows n8n e sincronizacoes assicronas.

Nao tratar produto expandido como bloqueador do MVP, salvo pedido explicito do usuario.

Fora do MVP salvo decisao posterior:

- inscricao oficial dentro do Tenfy como substituto da federacao;
- ranking oficial proprio;
- marketplace financeiro real;
- split/repasse;
- automacao completa sem revisao;
- integracao com todas as federacoes;
- dados fechados atras de login, captcha, paywall ou bloqueio tecnico.

## 3. Arquitetura real

```text
frontend/ Vite React TypeScript
mobile/   Expo React Native TypeScript
backend/  Django 5 + DRF + Celery + PostgreSQL + Redis
docs/     documentacao operacional e historica
*.json    exports n8n de sincronizacao de inscritos
scraping/ copia/referencia local de scraper externo, nao fonte canonica deste repo
```

Fluxo principal:

```text
Web/Mobile -> API Django -> PostgreSQL
                    |
                    +-> Redis/Celery/Beat
                    +-> Asaas, Resend, Cloudinary, Sentry
                    +-> n8n via endpoints com X-Import-Token
                    +-> MongoDB de scrapers externos para COSAT/ITF
```

Apps Django instalados:

- `accounts`: usuario customizado, JWT, OTP, LGPD, avatar, coach/athlete, parent/child, dependent invites.
- `players`: perfil esportivo, categorias canonicas, cache Tenis Integrado, UTR.
- `sources`: organizacoes e fontes de dados.
- `tournaments`: torneios, edicoes, categorias, links, eventos de alteracao.
- `eligibility`: regras, versoes, clausulas e avaliacao de compatibilidade.
- `watchlist`: agenda/favoritos e resultados vinculados.
- `alerts`: preferencias, alertas, push subscriptions.
- `ingestion`: conectores, runs, artifacts, persistencia e sync Mongo.
- `registrations`: inscricoes internas, entries de federacoes, importacao, matching.
- `billing`: planos, features, assinaturas, familia, pagamentos, webhooks Asaas.
- `admin_panel`: APIs operacionais do painel.
- `audit`: logs de auditoria.
- `marketplace`: base futura, nao assumir operacao financeira real.

## 4. Scraping externo e MongoDB

Regra central: scraping COSAT/ITF e de outro repositorio/servico. Nao implementar crawler pesado dentro do backend principal.

Fluxo COSAT oficial:

```text
servico crawler externo (ex: bWSantos7/crawler.git)
-> MongoDB dedicado
-> backend/apps/ingestion/management/commands/sync_cosat_from_mongo.py
-> PostgreSQL
-> API/app
```

Fluxo ITF oficial:

```text
servico scraper externo
-> MongoDB dedicado ou compartilhado via variaveis ITF_MONGO_*
-> sync_itf_from_mongo.py
-> PostgreSQL
-> API/app
```

O diretario `scraping/` pode aparecer no workspace, mas neste repo ele deve ser tratado como copia/referencia operacional. Se o usuario pedir mudanca real no scraper, confirmar se deve ser feita no repositorio do scraper. Aqui, normalmente so se ajusta:

- contratos de leitura Mongo;
- comandos `sync_cosat_from_mongo` e `sync_itf_from_mongo`;
- conectores Mongo em `backend/apps/ingestion/connectors/*_mongo.py`;
- documentacao e variaveis.

Nunca logar `COSAT_MONGO_URL`, `ITF_MONGO_URL` ou credenciais.

## 5. n8n e arquivos Sync

Os arquivos abaixo rodam no n8n:

- `Sync CBT Inscritos.json`
- `Sync FBT Inscritos.json`
- `Sync FPT (SP) Inscritos.json`

Eles seguem o desenho:

```text
Schedule/Cron
-> GET /api/integrations/federation-sync-targets/?source=...&needs_sync=true&limit=50
-> normalizar targets
-> buscar pagina da fonte quando necessario
-> POST /api/integrations/parse-entries/
-> validar parse quality_gate
-> POST /api/registrations/import/ com dry_run=true
-> validar dry_run quality_gate
-> POST /api/registrations/import/ com dry_run=false
-> PATCH /api/tournaments/editions/{id}/sync-state/
```

Regras n8n:

- Token apenas via env do n8n: `TENNIS_IMPORT_TOKEN`.
- Header correto: `X-Import-Token`.
- Nunca hardcodar token no JSON.
- Nao salvar se `parser_warning=true`.
- Nao salvar se `quality_gate.can_save=false`.
- Nao salvar se `entries_count=0`.
- Nao salvar se houver erros.
- Manter workflows por fonte; nao misturar CBT, FBT, FPT, COSAT e ITF no mesmo fluxo sem decisao explicita.
- Conferir dominio antes de importar/exportar workflow. A API correta/canonica e `https://api.tenfy.com.br`. Nao trocar para dominios antigos, staging ou Railway sem validar ambiente alvo.

COSAT nao deve usar n8n como fluxo oficial. Se encontrar docs antigas de COSAT via n8n, tratar como historico/obsoleto e preferir `docs/integrations/cosat_mongo_sync.md`.

## 6. Ingestao e dados externos

Principios:

- Usar dados publicos, dados fornecidos por admin ou dados importados por pipeline validado.
- Nao burlar login, captcha, paywall, rate limit ou bloqueio tecnico.
- Preferir API/documento publico/importacao assistida a scraping fragil.
- Preservar origem: `official_source_url`, `source_url`, `source_name`, `source_label`, `fetched_at`, `synced_at`, `confidence`, `raw_payload`, `validation_errors`, artifacts ou logs.
- Quando a fonte nao trouxer informacao, usar `unknown`, `null`, "nao informado" ou mensagem amigavel.
- Dados de ranking e pagamento so podem aparecer quando a fonte fornece ou admin valida.

Campos importantes:

- `TournamentEdition.official_source_url`: fonte oficial do torneio.
- `entries_source_url`: melhor URL conhecida para lista de inscritos.
- `candidate_entry_links`: candidatos para inscritos/chaves/ranking.
- `needs_sync`, `last_synced_at`, `sync_priority`, `parser_available`, `parser_limitation`: controle de sync.
- `FederationEntry`: lista publicada por federacao/fonte.
- `TournamentRegistration`: inscricao interna/auto-descoberta associada a perfil.
- `removed_or_replaced=true` prevalece sobre `payment_status=paid`.

Parsers atuais:

- `cbt`, `fct`, `fpt`, `fbt`: usam TenisIntegrado quando possivel e parser generico HTML/CSV como fallback.
- `cosat`: limitado; fluxo oficial e Mongo, import manual apenas como fallback.
- `manual`: usado para conteudo colado/CSV sob responsabilidade administrativa.

## 7. Backend Django

Comandos comuns:

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_plans
python manage.py seed_sources
python manage.py runserver
```

Checks e testes:

```bash
cd backend
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --keepdb
```

Testes direcionados:

```bash
python manage.py test apps.accounts
python manage.py test apps.players
python manage.py test apps.tournaments
python manage.py test apps.eligibility
python manage.py test apps.registrations
python manage.py test apps.ingestion
python manage.py test apps.billing
python manage.py test apps.alerts
python manage.py test apps.watchlist
python manage.py test apps.admin_panel
```

Configuracoes criticas:

- `DATABASE_URL` e obrigatorio e deve ser PostgreSQL. SQLite e bloqueado.
- `SECRET_KEY` deve existir e ter tamanho seguro.
- `DEBUG` tem parser estrito; valores invalidos quebram startup.
- Em teste, cache vira locmem e Celery usa broker em memoria.
- `IMPORT_API_TOKEN` autentica n8n/pipelines externos.
- `ASAAS_WEBHOOK_TOKEN` e obrigatorio para aceitar webhooks Asaas.
- `COSAT_MONGO_ENABLED` e `ITF_MONGO_ENABLED` controlam syncs Mongo.

Nao criar endpoint sem permissao. Conferir sempre serializer, view, url, permission, teste e impacto web/mobile.

## 8. Celery, Beat e operacoes

Servicos esperados no Railway:

- backend web com Gunicorn;
- worker Celery;
- beat Celery com `django_celery_beat`;
- PostgreSQL;
- Redis;
- frontend;
- servicos externos de crawler/Mongo quando habilitados.

Tarefas importantes:

- `apps.ingestion.tasks.run_all_active_sources`
- `apps.ingestion.tasks.detect_tournament_changes`
- `apps.ingestion.tasks.sync_cosat_from_mongo_task`
- `apps.ingestion.tasks.sync_itf_from_mongo_task`
- `apps.registrations.tasks.match_federation_entries`
- `apps.registrations.tasks.match_new_profile_to_entries`
- `apps.registrations.tasks.sync_fpt_sp_entries_task`
- `apps.registrations.tasks.sync_cbt_fct_entries_task`
- `apps.alerts.tasks.dispatch_deadline_alerts`
- `apps.players.tasks.sync_all_ti_profiles_task`
- `apps.players.tasks.sync_all_utr_profiles_task`

Comandos operacionais:

```bash
cd backend
python manage.py setup_periodic_tasks
python manage.py sync_cosat_from_mongo
python manage.py sync_cosat_from_mongo --no-dry-run --import-entries
python manage.py sync_itf_from_mongo
python manage.py sync_itf_from_mongo --no-dry-run --import-entries
```

`dry_run` e o padrao seguro. Nao rodar `--no-dry-run` em producao sem entender impacto e ter autorizacao.

## 9. Billing, planos e Asaas

Planos canonicos:

- `individual`
- `familia`
- `tester`

Nao recriar `free`, `pro`, `elite`, `basic` ou planos legados como produto novo. Se aparecerem no banco/codigo, tratar como legado/migracao.

Plano `tester`:

- interno/operacional;
- nao comercial;
- ativa imediatamente;
- nao exige Asaas;
- nao deve aparecer como plano publico normal.

Regras Asaas:

- Toda integracao Asaas fica no backend.
- Frontend/mobile nunca recebem `ASAAS_API_KEY`.
- Backend aceita `card_token`, nunca dados crus de cartao.
- Assinatura paga so ativa por webhook/confirmacao real.
- Pix retorna apenas QR code, copia e cola, status e IDs seguros.
- Webhook valida token com comparacao segura.
- Dados PCI sensiveis nao podem ser persistidos.

Antes de mexer em billing, ler:

- `backend/apps/billing/models.py`
- `backend/apps/billing/views.py`
- `backend/apps/billing/services/asaas_service.py`
- `backend/apps/billing/permissions.py`
- `backend/apps/billing/tests.py`
- `backend/apps/billing/management/commands/seed_plans.py`

## 10. Frontend web

Stack:

- Vite;
- React 18;
- TypeScript;
- Tailwind;
- React Router;
- Axios;
- Zustand;
- Recharts;
- Playwright e2e.

Comandos:

```bash
cd frontend
npm install
npm run dev
npm run build
npm run test:e2e
```

Rotas principais:

- `/`: landing;
- `/login`, `/register`, recuperacao/reset de senha;
- `/inicio`;
- `/torneios`, `/torneios/:id`, `/comparar`;
- `/watchlist`, `/resultados`, `/alertas`;
- `/perfil`, `/configuracoes`;
- `/assinatura`, `/inscricoes`, `/treinador`;
- `/admin-panel`.

Regras:

- `VITE_API_BASE_URL` deve apontar para a API correta.
- Nao colocar secrets no frontend.
- Usar mensagens amigaveis; nao vazar nomes tecnicos de campos, SQL, stack trace ou paths.
- Tratar loading, erro e vazio.
- Preservar responsividade e consistencia visual.
- Nao usar mock para esconder erro real em producao.

## 11. Mobile Expo

Stack:

- Expo 54;
- React Native 0.81;
- React 19;
- React Navigation;
- SecureStore;
- NetInfo;
- Expo fonts Poppins;
- Axios.

Comandos:

```bash
cd mobile
npm install
npm run typecheck
npx expo start
```

Builds:

```bash
npm run build:android:preview
npm run build:android:prod
npm run build:ios:prod
```

Regras:

- Usar `EXPO_PUBLIC_API_BASE_URL`; a API correta/canonica e `https://api.tenfy.com.br`.
- Tokens ficam no SecureStore.
- Nao implementar regra critica so no app.
- Fluxo de pagamento pendente bloqueia abas ate assinatura ativa.
- Responsavel/dependente deve respeitar perfil ativo e isolamento de dados.
- Telas devem ter loading, erro, vazio e teclado bem tratado.
- Nao exibir textos tecnicos ao usuario.

## 12. Elegibilidade, torneios e perfis

Elegibilidade e apoio ao jogador, nao validacao oficial da federacao.

Ao mexer em compatibilidade:

- conferir `players.PlayerProfile`;
- conferir `players.PlayerCategory`;
- conferir `tournaments.filters`;
- conferir `eligibility.services` e `eligibility.services_normalize`;
- conferir serializers/listagens que mostram `eligibility`;
- testar com jogador individual, responsavel e dependente.

Nao afirmar "voce esta oficialmente elegivel" quando regra/ranking da fonte for incompleto. Usar linguagem de potencial, compatibilidade ou incerteza.

## 13. Inscricoes, entries e matching

Conceitos:

- `FederationEntry`: dado publicado/importado de fonte externa.
- `TournamentRegistration`: inscricao associada a perfil Tenfy.
- `MatchingLog`: auditoria do matching automatico.
- `WatchlistItem`: agenda/status do usuario.

Fluxo esperado apos import real:

```text
FederationEntry salvo
-> match_federation_entries
-> tenta match por external_id
-> tenta match fuzzy de nome com alta confianca
-> cria TournamentRegistration se aplicavel
-> cria/atualiza WatchlistItem
-> registra MatchingLog
```

Regras:

- Match fuzzy precisa ser conservador.
- Nao misturar dados entre dependentes.
- Se entry removida/substituida, refletir retirada em registration/watchlist quando houver match.
- Lista publica de inscritos pode ser exibida quando a fonte publica permitir, sem dados sensiveis indevidos.

## 14. Admin e auditoria

Painel admin deve:

- exigir usuario staff/admin;
- nao quebrar sem dados;
- mostrar estados operacionais de conectores;
- permitir revisao/publicacao/ocultacao de torneios;
- disparar syncs apenas quando seguro;
- nao expor tokens, payloads sensiveis ou stack traces.

Auditoria deve ser usada para acoes sensiveis quando aplicavel: usuario, assinatura, fontes, edicoes, importacoes e operacoes admin.

## 15. Seguranca e privacidade

Obrigatorio:

- Nao commitar `.env`.
- Nao commitar exports n8n com tokens reais.
- Nao expor secrets em frontend/mobile.
- Nao usar SQLite.
- Nao deixar `DEBUG=True` em producao.
- Nao usar `ALLOWED_HOSTS=*`.
- Nao aceitar webhook sem token.
- Nao salvar dados crus de cartao.
- Nao registrar PII/secrets no Sentry ou logs.
- Nao exibir dados de menores/dependentes sem permissao.
- Confirmar exclusoes destrutivas.
- Usar `hmac.compare_digest` para tokens sensiveis.

LGPD:

- coletar o minimo necessario;
- respeitar consentimento;
- permitir exportacao/exclusao quando disponivel;
- proteger dados de dependentes;
- usar mensagens claras para impacto de exclusao.

## 16. Dominios e ambientes

Dominios finais preferenciais:

```text
Frontend: https://www.tenfy.com.br
API:      https://api.tenfy.com.br
```

Referencias a outros dominios podem aparecer em docs ou codigo antigo. Tratar como legado/staging ate o usuario confirmar o contrario.

Local:

```text
Backend:  http://localhost:8000
Frontend: http://localhost:5173
Mobile:   Expo dev server
```

## 17. Testes e validacao por area

Backend:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --keepdb
```

Frontend:

```bash
npm run build
npm run test:e2e
```

Mobile:

```bash
npm run typecheck
npx expo start
```

Validar conforme alteracao:

- auth/cadastro/OTP/reset;
- perfil esportivo;
- responsavel/dependentes;
- torneios/lista/filtros/detalhe;
- compatibilidade;
- watchlist/agenda/resultados;
- inscritos publicos;
- importacao e matching;
- billing/checkout/webhook/planos/familia;
- admin panel;
- alertas/push;
- responsividade.

Se nao rodar teste aplicavel, explicar motivo.

## 18. Processo antes de alterar codigo

1. Ler este arquivo.
2. Entender pedido do usuario e classificar: MVP, produto expandido, pos-MVP, dependencia externa ou limitacao da fonte.
3. Localizar arquivos envolvidos com `rg`.
4. Ler models, serializers, views, services/tasks e telas antes de editar.
5. Verificar impacto backend/web/mobile/n8n.
6. Preservar mudancas locais do usuario. Nao reverter diff alheio.
7. Planejar menor alteracao que resolve a causa raiz.
8. Se envolver producao, dados reais, pagamentos, migration ou import real, confirmar autorizacao quando houver risco.

## 19. Processo depois de alterar codigo

1. Rodar checks/testes aplicaveis.
2. Conferir `git diff`.
3. Conferir se nao ha secrets.
4. Conferir permissoes/autenticacao.
5. Conferir mensagens ao usuario.
6. Conferir compatibilidade com web/mobile quando API muda.
7. Documentar mudanca, causa, testes e riscos.

Resposta final esperada para tarefas de codigo:

```text
Resumo:
Arquivos alterados:
Como validar:
Testes executados:
Riscos/pendencias:
```

Para revisoes, listar achados primeiro, com arquivo/linha e severidade.

## 20. Comandos uteis

```bash
rg --files
rg "texto" backend frontend mobile docs
git status --short
git diff --stat
git diff -- <arquivo>
```

Backend:

```bash
cd backend
python manage.py check
python manage.py test apps.billing --keepdb
python manage.py seed_plans
python manage.py setup_periodic_tasks
```

Syncs seguros:

```bash
python manage.py sync_cosat_from_mongo --limit 5
python manage.py sync_itf_from_mongo --limit 5
```

Syncs reais exigem cuidado:

```bash
python manage.py sync_cosat_from_mongo --no-dry-run --import-entries
python manage.py sync_itf_from_mongo --no-dry-run --import-entries
```

## 21. Armadilhas conhecidas

- `scraping/` no workspace nao significa que o scraper seja parte canonica deste repo.
- JSONs `Sync ... Inscritos` sao workflows n8n; alterar arquivo local nao altera o n8n em execucao ate importar/publicar workflow.
- COSAT via n8n e obsoleto; usar Mongo sync.
- Alguns docs antigos citam Tenfy/Tennis e dominios diferentes. Conferir contexto antes de padronizar.
- `dry_run` pode chegar como string; backend ja tenta parsear, mas workflows devem mandar boolean real.
- `player_external_id` vazio pode causar dedup ruim; o backend gera ID deterministico, mas preferir ID real da fonte.
- `removed_or_replaced` sempre ganha de pagamento pago.
- Testes locais exigem PostgreSQL; nao trocar para SQLite.
- Nao corrigir "mojibake" ou encoding em massa junto com tarefa funcional sem pedido explicito, para evitar diff ruidoso.
- Nao rodar comandos destrutivos de banco ou limpeza em producao sem confirmacao.

## 22. Prioridade do projeto

1. Seguranca e privacidade.
2. Dados reais, rastreaveis e sem invencao.
3. MVP contratual.
4. Estabilidade da API.
5. Calendario e detalhe de torneios.
6. Elegibilidade clara e honesta.
7. Assinaturas/Asaas corretas.
8. Responsavel/dependentes sem vazamento de dados.
9. Ingestao/importacao com `dry_run` e qualidade.
10. UX limpa no web/mobile.
11. Operacao n8n e Mongo sem segredos.
12. Custos controlados.

Trate o Tenfy como produto real em producao. Toda mudanca deve melhorar confiabilidade, clareza ou entrega sem criar risco oculto.
