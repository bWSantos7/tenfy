# Relatório de Implementação: Torneios Kids (visibilidade por perfil Criança)

Data: 2026-07-12. Branches: `tester` (tenfy) e `tester` (sync), ainda não mergeadas.

Este documento registra a implementação completa da categoria **Kids** (torneios
para jogadores abaixo de 12 anos) no ecossistema Tenfy: extração de dados no
`tournament-extractor` (repositório `sync`), ingestão/classificação no backend
Tenfy, e visibilidade condicionada ao perfil do jogador (`competitive_level =
kids`, tela "Nível competitivo" → **Crianças**) no frontend web e mobile.

Documento irmão no repositório `sync`: `docs/RELATORIO_TORNEIOS_KIDS.md`.

---

## 1. Objetivo e regra de negócio

> "Torneios kids devem aparecer somente para o usuário que tenha o perfil
> criado como kid ou Criança." — pedido original do usuário.

Antes desta implementação, o Tenfy só reconhecia a faixa **Juvenil (12–18
anos)** via `TournamentEdition.is_youth`. Torneios puramente Kids (abaixo de
12 anos, sem nenhuma categoria 12–18) não eram sequer extraídos pelo
`tournament-extractor`, e não existia nenhum mecanismo de visibilidade
condicionada ao nível competitivo do jogador.

Fontes com Kids confirmado: **CBT** (nacional), **Federações estaduais**
(FPT-SP, FGT, FCT-SC, FCT, FGOT, FPBT, FTRO, FMT, FSET, FCET, FPET, FTMT — 12
federações com dados reais hoje), **FPT** (já buscava Kids na API, só não
persistia). **COSAT e ITF confirmados sem Kids** (COSAT trata exclusivamente
12–18; ITF Juniors é por definição 12–18) — nenhuma mudança nessas duas
fontes.

---

## 2. Backend Tenfy — mudanças

### 2.1 Modelo e migration
- `backend/apps/tournaments/models.py`: novo campo `TournamentEdition.is_kids`
  (`BooleanField, default=False, db_index=True`), paralelo ao `is_youth` já
  existente.
- `backend/apps/tournaments/migrations/0013_tournamentedition_is_kids.py`.

### 2.2 Leitura do extractor (`apps/ingestion/connectors/extractor_reader.py`)
- `iter_tournaments()` passa a incluir torneios com `is_kids=TRUE` mesmo
  quando `is_youth=FALSE` (torneios 100% Kids, sem categoria 12–18):
  `WHERE (t.is_youth = TRUE OR COALESCE(t.is_kids, FALSE) = TRUE)`.
- **Segurança de ordem de deploy**: como Tenfy e `sync` são deployados
  independentemente, `_has_tournaments_is_kids_column()` checa
  `information_schema.columns` antes de referenciar `is_kids` no SQL. Se a
  coluna ainda não existir no banco do extractor (deploy do Tenfy foi ao ar
  primeiro), cai de volta no filtro antigo (`is_youth = TRUE`) em vez de
  quebrar todo o sync.

### 2.3 Classificação (`apps/ingestion/persistence.py`)
- `_classify_is_kids(circuit, title, categories, source_name, extractor_is_kids=None)`:
  quando o extractor já manda a classificação (`extractor_is_kids` não-nulo),
  ela tem prioridade sobre o heurístico de texto (`_KIDS_KEYWORDS`).
- `_classify_is_youth(...)` ganhou o mesmo parâmetro `extractor_is_youth`,
  mesma prioridade — necessário porque o heurístico de texto antigo tratava
  "kids"/idade 8–18 como youth em bloco, o que conflitava com o novo
  `is_kids` granular vindo do extractor.
- `sync_from_extractor.py`: `_build_edition_data()` propaga `is_youth`/
  `is_kids` do dicionário do extractor para o payload de criação/atualização.

### 2.4 Visibilidade por perfil (`apps/tournaments/filters.py`)
`TournamentEditionFilter.filter_player_level()` (parâmetro `?player_level=`,
enviado pelo frontend a partir de `PlayerProfile.competitive_level`):

| Nível do perfil | Regra |
|---|---|
| `kids` (Crianças) | `is_kids=True` OU `is_youth=True` OU `is_youth` nulo — mantém a visibilidade ampla que já existia pro infantojuvenil, mais os 100% Kids |
| `youth` (Juvenil) | `is_youth=True`/nulo, excluindo o que é **exclusivamente** Kids (torneio misto Kids+Juvenil continua visível) |
| `pro`/`seniors` | `is_youth=False`/nulo, excluindo **sempre** `is_kids=True` (mesmo torneio misto não faz sentido pra perfil adulto) |

### 2.5 Categorias normalizadas (`apps/players/management/commands/seed_player_categories.py`)
- Adicionadas categorias Kids de idade exata `5, 6, 7, 8, 9, 11` (10 já
  existia) em `TAXONOMY_KIDS` — os dados reais de CBT/Federações/FPT trazem
  majoritariamente essas idades, não só 12/14/16/18.

### 2.6 Admin (`apps/admin_panel/views.py`)
- `is_kids` exposto em `EditionPatchSerializer`, `AdminEditionListSerializer`,
  `EditionCreateSerializer`. Confirmado que a listagem admin **não** esconde
  torneios 100% Kids por padrão (`youth_only` é opt-in, default `false` —
  "admin precisa ver tudo").

### 2.7 Correção lateral (`apps/sources/management/commands/fix_federation_orgs.py`)
- Troca de seta unicode `→` por `->` — causava `UnicodeEncodeError` real no
  console Windows (cp1252) ao rodar a suíte completa de testes.

---

## 3. Frontend web — mudanças

- `frontend/src/types/index.ts`: campo `is_kids: boolean` em
  `TournamentEditionList`.
- `frontend/src/pages/HomePage.tsx`: `filterByLevel()` — mirror client-side
  da regra do backend (ver bugs corrigidos abaixo).
- `TournamentsPage.tsx` **já estava correto**: já resolvia o perfil ativo
  (inclusive do dependente selecionado por um responsável, via
  `getActiveProfileId`) e enviava `player_level` + `profile_id` em toda
  chamada — não precisou de mudança.
- Mobile (`mobile/src/WebAppShell.tsx`) é uma casca WebView do frontend web
  — sem lógica própria de `player_level`/`is_kids`, herda os fixes
  automaticamente.

---

## 4. Bugs reais encontrados e corrigidos

Todos encontrados por leitura de código ponta a ponta (não só rodando a
suíte de testes) e confirmados ao vivo contra a API de staging antes de
considerar corrigidos.

### 4.1 Detalhe do torneio 404ava para torneios 100% Kids
`TournamentDetailPage.tsx` (`getEdition()`) não envia `player_level`. O
`get_queryset()` do backend, sem esse parâmetro, cai no filtro padrão
`is_youth=True OU nulo` — que exclui torneios 100% Kids (`is_youth=False`).
Resultado: um torneio 100% Kids visível na listagem (`?player_level=kids`)
retornava 404 ao abrir o detalhe.

**Fix**: `apps/tournaments/views.py` — o filtro padrão passa a não se
aplicar ao `retrieve` (mesmo padrão já usado pro escopo de federação, que já
tinha essa exceção documentada no código). Quem já apareceu numa listagem
pode ser aberto.

### 4.2 Home ("Encerrando em breve"/"Recentes") escondia torneios 100% Kids
`closingSoon()`/`listEditions()` na Home não enviavam `player_level` — só
`profile_id`. Mesma causa raiz do bug 4.1: o servidor removia os torneios
100% Kids **antes** do filtro client-side (`filterByLevel`) sequer rodar.

**Fix**: `HomePage.tsx` — `player_level` agora é enviado nas duas chamadas.

### 4.3 Troca de dependente ativo (`switchProfile`) tinha o mesmo problema
Ao alternar entre dependentes, o responsável disparava um novo
`closingSoon()` sem `player_level` **e sem aplicar `filterByLevel`** no
resultado — dupla falha.

**Fix**: `player_level` incluído na chamada + `filterByLevel`/
`filterByModality` aplicados ao resultado.

### 4.4 [Crítico, no repo `sync`] Coluna `is_kids` nunca seria criada em produção
Ver seção 3 do relatório irmão (`sync/docs/RELATORIO_TORNEIOS_KIDS.md`).
Resumo: `create_all()` do SQLAlchemy não altera tabelas já existentes;
`init_db()` agora aplica o `ALTER TABLE ADD COLUMN IF NOT EXISTS` de forma
idempotente a cada deploy.

---

## 5. Reestruturação de branches e Railway

A pedido do usuário, os dois repositórios foram consolidados para **duas
branches permanentes**:

- **tenfy**: `master` (produção) e `tester` (staging/integração).
- **sync**: `main` (produção) e `tester` (staging/integração).

Branches antigas removidas: `feat/kids-tournaments-visibility` e `tester`
obsoleto (tenfy), `chore/django-52-lts` (tenfy, já mergeada), `staging`
(sync). O trabalho de cada uma foi preservado renomeando a branch ativa para
`tester` antes de apagar as demais.

Os 3 serviços de deploy em staging (Railway, projeto `staging_tenfy`) —
`backend`, `frontend` (ambos do tenfy) e `sync` — foram reconectados para
acompanhar a branch `tester` de cada repositório. Root Directory
(`/backend`, `/frontend`) preservado; todos os builds concluíram com
sucesso.

PRs (fechados e recriados após a renomeação de branch, pois o GitHub fecha
automaticamente o PR quando a branch de origem é apagada):
- tenfy: **PR #88** `tester → master` — https://github.com/bWSantos7/tenfy/pull/88
- sync: **PR #2** `tester → main` — https://github.com/bWSantos7/sync/pull/2

---

## 6. Testes executados

| Suíte | Resultado |
|---|---|
| `python manage.py test --keepdb` (backend, suíte completa) | **863/863 OK** |
| `python manage.py check` / `makemigrations --check --dry-run` | Sem issues, sem drift |
| `npm run build` (frontend, tsc + vite) | Build limpo |
| Testes novos (`PlayerLevelKidsFilterTestCase`, `KidsCategoryNormalizationTestCase`, `test_retrieve_kids_only_nao_404_sem_player_level`, `ExtractorSchemaWithoutIsKidsColumnTest`) | Cobrem: aceitação por nível, normalização de categoria por idade exata, regressão do 404 no detalhe, comportamento antes da migration existir |

### Validação ao vivo contra staging (não só testes automatizados)
Login real como conta de teste (`kidstest@tenfy.com.br`, perfil Crianças,
federação FPT-SP) contra a API de staging:

| Chamada | Resultado |
|---|---|
| `closing_soon` com `player_level=kids` | 8 torneios 100% Kids retornados |
| `editions/` com `player_level=kids` | 31 torneios 100% Kids (bate exato com a contagem esperada pra FPT-SP) |
| `editions/` **sem** `player_level` (simulando o bug antigo) | 0 — confirma que o bug existia antes do fix |
| `editions/137/` (torneio 100% Kids) sem `player_level`, como `getEdition()` chama hoje | HTTP 200 (antes: 404) |

---

## 7. Contagem de torneios Kids sincronizados em staging (dados reais)

| Federação | Sigla | Torneios Kids |
|---|---|---|
| Federação Paulista de Tênis | FPT-SP | 33 |
| Federação Gaúcha de Tênis | FGT | 12 |
| Federação Catarinense de Tênis | FCT-SC | 12 |
| CBT (nacional) | CBT | 9 |
| Federação Carioca de Tênis | FCT | 8 |
| Federação Goiana de Tênis | FGOT | 5 |
| Federação Paraibana de Tênis | FPBT | 3 |
| Federação de Tênis de Rondônia | FTRO | 3 |
| Federação Mineira de Tênis | FMT | 2 |
| Federação Sergipana de Tênis | FSET | 2 |
| Federação Cearense de Tênis | FCET | 1 |
| Federação Pernambucana de Tênis | FPET | 1 |
| Federação Mato-grossense de Tênis | FTMT | 1 |
| **Total** | | **92** |

Ambiente de staging: `https://frontend-production-0384.up.railway.app`.
Conta de teste: `kidstest@tenfy.com.br` / `TenfyKids2026!` (perfil Crianças,
federação FPT-SP).

---

## 8. Pendências

- **Nenhuma pendência técnica bloqueante.** As duas PRs (#88 tenfy, #2 sync)
  estão `MERGEABLE`/`CLEAN`, com CI verde, prontas para merge.
- Merge para produção (`master`/`main`) **não foi executado** — aguardando
  decisão explícita do usuário, conforme combinado ("testar... e depois
  fazermos o merge").
- Validação visual em navegador (clique real na UI da Home/torneios com a
  conta Kids) ainda não foi feita por mim — a validação foi via API direta
  (mesmos dados que a UI consome), não substitui um clique real na tela.
- Verificação manual do usuário na federação Paulista em staging já
  solicitada anteriormente; resultado não reportado de volta nesta sessão.
