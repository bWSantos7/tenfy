# COSAT — Sincronização via MongoDB do Crawler

## Arquitetura oficial

```
[cosat.tournamentsoftware.com]
       │
       ▼ (crawler Railway — bWSantos7/crawler.git, roda a cada 6h)
[MongoDB exclusivo do crawler]
  ├── collection: tournaments  (cosatId, name, url, events, dateRange…)
  ├── collection: players      (name, tournamentId, profileId, rankingCategory…)
  └── collection: rankingentries (playerName, rank, category, sourceUrl…)
       │
       ▼ (management command — backend Django)
[sync_cosat_from_mongo]
       │
       ▼
[PostgreSQL — fonte oficial Tennis Hub]
  ├── TournamentEdition (external_id=cosat:{cosatId}, circuit=COSAT)
  └── FederationEntry   (source=cosat, confidence=medium/high)
       │
       ▼
[API / App]
```

**COSAT NÃO usa n8n.** O n8n é utilizado apenas para CBT e FBT.

---

## Variáveis Railway (backend service)

```
COSAT_MONGO_ENABLED=true
COSAT_MONGO_URL=${{MongoDB.MONGO_URL}}           # URL interna Railway do serviço crawler
COSAT_MONGO_DB=<nome_do_banco_no_crawler>        # confirmar com owner do serviço crawler
COSAT_MONGO_COLLECTION_TOURNAMENTS=tournaments   # default correto
COSAT_MONGO_COLLECTION_ENTRIES=players           # default correto
COSAT_MONGO_COLLECTION_RANKINGS=rankingentries   # default correto
COSAT_MONGO_CONNECT_TIMEOUT_MS=5000              # opcional, default 5000
```

> **Segurança:** `COSAT_MONGO_URL` nunca aparece em logs — a URL é sanitizada antes de qualquer saída.

---

## Comandos de sincronização

### Dry-run (seguro, padrão)

Mostra o que seria importado sem salvar nada:

```bash
python manage.py sync_cosat_from_mongo
# ou explicitamente:
python manage.py sync_cosat_from_mongo --dry-run
```

### Dry-run com limite

```bash
python manage.py sync_cosat_from_mongo --limit 5
```

### Dry-run torneio específico

```bash
python manage.py sync_cosat_from_mongo --tournament-id <cosatId>
```

### Sync real — torneios

```bash
python manage.py sync_cosat_from_mongo --no-dry-run
```

### Sync real — torneios + inscritos

```bash
python manage.py sync_cosat_from_mongo --no-dry-run --import-entries
```

> Entries de torneios COSAT já existentes no PostgreSQL também são atualizadas
> (não apenas as do run atual).

### Sync real — torneio específico + inscritos

```bash
python manage.py sync_cosat_from_mongo --no-dry-run --import-entries --tournament-id <cosatId>
```

---

## O que é sincronizado

| Dado | Collection Mongo | Destino PostgreSQL | Observação |
|---|---|---|---|
| Torneios | `tournaments` | `TournamentEdition` | `external_id=cosat:{cosatId}` |
| Categorias | `events[]` (embedded) | `TournamentCategory` | via `TournamentPersister` |
| Inscritos | `players` | `FederationEntry` | só com `--import-entries` |
| Rankings | `rankingentries` | — | **NÃO importados** nesta fase (sem FK confiável para TournamentEdition) |

---

## Rankings — status atual

Os rankings da collection `rankingentries` **não são importados** pelo comando de sync.
Motivo: documentos de ranking não possuem `tournamentId` confiável para vincular com
uma `TournamentEdition` específica.

Futuramente: quando o crawler expor linkagem torneio↔ranking, adicionar flag `--import-rankings`.

---

## Campos mapeados

### Tournament → TournamentEdition

| Campo Mongo | Campo Django | Obs |
|---|---|---|
| `cosatId` | `external_id = 'cosat:{cosatId}'` | chave de dedup |
| `name` | `title`, `canonical_name` | |
| `url` | `official_source_url` | |
| `dateRange` | `start_date`, `end_date` | parsing "10 - 15 Nov 2025" |
| `events[].name` | `TournamentCategory.source_text` | |
| `location` | `venue.city`, `venue.state` | parsing "Buenos Aires, AR" |
| `lastUpdated` | `synced_at` (via auto_now) | |

### Player → FederationEntry

| Campo Mongo | Campo Django | Obs |
|---|---|---|
| `name` | `player_name` | |
| `profileId` ou `tournamentPlayerId` | `player_external_id = 'cosat:{id}'` | preferência: profileId |
| `rankingCategory` | `category_text` | rejeitado se vazio |
| — | `payment_status = 'unknown'` | crawler não captura pagamento |
| — | `source = 'cosat'` | |
| — | `confidence = 'medium'` | |

> Entradas sem `category_text` são **rejeitadas** — nunca inventamos categoria.

---

## Verificar dados após sync

```bash
# Torneios COSAT no PostgreSQL
python manage.py shell -c "
from apps.tournaments.models import TournamentEdition
print(TournamentEdition.objects.filter(external_id__startswith='cosat:').count(), 'torneios COSAT')
"

# Inscritos COSAT
python manage.py shell -c "
from apps.registrations.models import FederationEntry
print(FederationEntry.objects.filter(source='cosat').count(), 'inscritos COSAT')
"

# Via API (após sync):
# GET /api/integrations/federation-sync-targets/?source=cosat
```

---

## Automação (Celery Beat — opcional futuro)

O comando pode ser agendado via Celery Beat ou cron no Railway. Por enquanto,
execução manual ou via deploy trigger. Não usar n8n para COSAT.

---

## Troubleshooting

| Sintoma | Causa provável | Solução |
|---|---|---|
| `COSAT_MONGO_ENABLED is False` | Variável não configurada | Setar `COSAT_MONGO_ENABLED=true` no Railway |
| `MongoDB is not reachable` | URL interna incorreta ou crawler offline | Verificar `COSAT_MONGO_URL` e status do serviço crawler |
| `COSAT_MONGO_DB is empty` | Variável não configurada | Setar `COSAT_MONGO_DB=<nome_do_banco>` |
| `tournaments_skipped: N` em dry-run | Normal — só mostra preview | Adicionar `--no-dry-run` para salvar |
| Entries não importadas | `--import-entries` ausente | Adicionar flag `--import-entries` |
| Player rejeitado sem categoria | Dado ausente no MongoDB | Normal — nunca inventar categoria |
