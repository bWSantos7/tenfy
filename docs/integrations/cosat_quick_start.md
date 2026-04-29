# COSAT Quick Start — Importar Inscritos em 10 Minutos

## Pré-requisitos

- Acesso ao painel Railway do Tennis Hub
- n8n instalado (cloud ou self-hosted)
- Acesso à página pública do torneio em `cosat.tournamentsoftware.com`

---

## Passo 1 — Gerar IMPORT_API_TOKEN

```bash
python -c "import secrets; print(secrets.token_hex(32))"
# Exemplo: 7f3a9c1d8e2b4f6a0c5d3e7f1a9b2c4d...
```

---

## Passo 2 — Configurar no Railway

1. Abrir Railway → serviço `backend` → aba **Variables**
2. Adicionar nova variável:
   ```
   IMPORT_API_TOKEN = <valor gerado no passo 1>
   ```
3. Railway faz redeploy automático (~1 min)

---

## Passo 3 — Testar autenticação

```bash
curl -s -X POST https://api.tennis.app.br/api/registrations/import/ \
  -H "Content-Type: application/json" \
  -H "X-Import-Token: SEU_TOKEN_AQUI" \
  -d '{"edition_id": 999, "entries": [{"player_name": "Teste", "category_text": "Sub-14 M"}]}' 
# Resposta esperada: {"detail": "Edição não encontrada."} com HTTP 404
# Se vier 403 → token errado ou IMPORT_API_TOKEN não configurado no Railway
```

---

## Passo 4 — Encontrar edition_id do torneio

**Opção A** — Painel admin:
1. Acesse `https://api.tennis.app.br/admin/`
2. Tournaments → Tournament editions
3. Copie o `id` do torneio desejado

**Opção B** — API:
```bash
curl -s "https://api.tennis.app.br/api/tournaments/editions/?q=nome+do+torneio" \
  -H "Authorization: Bearer SEU_JWT"
# Procure o campo "id" na resposta
```

---

## Passo 5 — Capturar dados do torneio COSAT

1. Abra `https://cosat.tournamentsoftware.com`
2. Localize o torneio
3. Acesse a seção **Entry List** ou **Draw**
4. Copie a tabela de inscritos (Ctrl+A → Ctrl+C ou salve como CSV)

---

## Passo 6 — Testar com dry_run=true

Use o arquivo `docs/examples/cosat_bulk_import_example.json` como base:

```bash
curl -s -X POST https://api.tennis.app.br/api/registrations/import/ \
  -H "Content-Type: application/json" \
  -H "X-Import-Token: SEU_TOKEN_AQUI" \
  -d @docs/examples/cosat_bulk_import_example.json
```

Resposta esperada:
```json
{
  "dry_run": true,
  "created": 4,
  "updated": 0,
  "errors": [],
  "warnings": [...],
  "detail": "[DRY RUN] Prévia: 4 seriam criadas, 0 atualizadas, 0 rejeitadas.",
  "previews": [...]
}
```

---

## Passo 7 — Confirmar importação real

Trocar `"dry_run": false` no payload e reenviar.

Resposta:
```json
{
  "dry_run": false,
  "created": 4,
  "updated": 0,
  "errors": [],
  "detail": "4 criadas, 0 atualizadas, 0 erros."
}
```

---

## Passo 8 — Validar no mobile

1. Abrir o app Tennis Hub
2. Navegar até o torneio importado
3. Tocar em **Ver inscritos**
4. Verificar: nome, categoria, ranking, status, fonte (COSAT), sync time

---

## Passo 9 — Configurar n8n para automação

1. Importar workflow: `docs/integrations/n8n_cosat_import_workflow.json`
2. Configurar variável de ambiente no n8n:
   ```
   TENNIS_HUB_IMPORT_TOKEN = <mesmo valor do IMPORT_API_TOKEN>
   ```
3. Ajustar `edition_id` no nó de configuração
4. Executar manualmente (Manual Trigger) ou agendar

---

## Erros comuns

| Erro | Causa | Solução |
|---|---|---|
| `HTTP 403` | Token errado/ausente | Verificar IMPORT_API_TOKEN no Railway |
| `HTTP 404 "Edição não encontrada"` | edition_id errado | Buscar ID correto no admin |
| `"player_name obrigatório"` | Linha sem nome | Verificar CSV/JSON |
| Atleta duplicado não esperado | player_external_id vazio | Sempre fornecer external_id |
| `HTTP 400 confidence inválido` | Valor fora de high/medium/low | Corrigir campo confidence |

---

## Dedup — evitar duplicatas

Chave única: `(edition_id, category_text, player_external_id, source)`

- Reimportar mesmo atleta = **atualiza** (safe)
- Sempre fornecer `player_external_id` para dedup correto
- `dry_run=true` mostra se seria criado ou atualizado antes de salvar

---

## Regra de substituição por ranking

Um atleta **pago** pode aparecer como **Removido** se a federação aplicar corte por ranking.
Usar `"removed_or_replaced": true` para marcar esses casos.
O app exibe: "Removido — critério de ranking" em vermelho.
