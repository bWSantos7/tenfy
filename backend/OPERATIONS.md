# Tenfy — Comandos Operacionais

Referência de comandos Django para operações recorrentes em produção e staging.
Todos os comandos devem ser executados no serviço **web** ou **worker** do Railway
(`railway run` ou via Railway CLI `railway exec`).

---

## Billing — Planos

### Seed / atualizar planos Individual e Família

```bash
python manage.py seed_plans
```

Cria ou atualiza os planos **Individual** (R$ 19,90/mês) e **Família** (R$ 34,90/mês)
e seus features. Idempotente — seguro de rodar em qualquer ambiente.

### Desativar planos legados (free / pro / elite)

```bash
python manage.py seed_plans --deactivate-old
```

Marca os planos com slug `free`, `pro` e `elite` como `is_active=False`.
Idempotente — se já estiverem inativos, não faz nada.

> **Quando rodar:** após confirmar que nenhum usuário ativo tem assinatura nesses
> planos. Verificar com:
> ```sql
> SELECT plan_id, count(*) FROM billing_subscription
> WHERE status = 'active'
> GROUP BY plan_id;
> ```

### Reset completo de planos (DESTRUTIVO — apenas dev/staging)

```bash
python manage.py seed_plans --reset
```

Apaga todos os planos, features e planfeatures antes de recriar. **Nunca usar em produção.**

---

## Ingestion — COSAT MongoDB

### Dry-run (padrão seguro)

```bash
python manage.py sync_cosat_from_mongo
```

Exibe o que seria sincronizado sem salvar nada. Sempre rodar antes do `--no-dry-run`.

### Sincronizar torneios

```bash
python manage.py sync_cosat_from_mongo --no-dry-run
```

### Sincronizar torneios + inscrições

```bash
python manage.py sync_cosat_from_mongo --no-dry-run --import-entries
```

### Sincronizar torneio específico

```bash
python manage.py sync_cosat_from_mongo --no-dry-run --tournament-id <cosatId>
```

---

## Migrations

```bash
python manage.py migrate
```

Sempre rodar após deploy que contenha novas migrations. O Railway executa isso
automaticamente se configurado no `release` command.

---

## Health check

```
GET /health/
```

Retorna 200 se o serviço está saudável. Usado pelo Railway healthcheck (timeout 300s).
