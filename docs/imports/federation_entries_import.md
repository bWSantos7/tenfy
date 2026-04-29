# Importação de Inscritos de Federações — Guia de Formato

## Endpoint

```
POST https://api.tennis.app.br/api/registrations/federation/bulk-import/
```

## Autenticação

Duas opções aceitas:

**Opção A — Token de importação (recomendado para n8n/scripts externos):**
```
X-Import-Token: <IMPORT_API_TOKEN>
```

**Opção B — JWT de admin (para uso via painel admin ou cURL manual):**
```
Authorization: Bearer <seu_jwt_staff>
```

## Colunas aceitas (JSON)

```
player_name           string   OBRIGATÓRIO — nome do atleta
category_text         string   OBRIGATÓRIO — categoria exata da federação
player_external_id    string   opcional    — ID único do atleta na federação (usado para dedup)
ranking_position      integer  opcional    — posição no ranking (menor = melhor)
ranking_source        string   opcional    — ex: "CBT 2026", "COSAT Jan/2026"
payment_status        string   opcional    — paid | pending | unknown (default: unknown)
removed_or_replaced   boolean  opcional    — true se removido por critério de ranking
replacement_reason    string   opcional    — motivo da remoção
notes                 string   opcional    — observações
source_url            string   opcional    — URL onde este inscrito foi encontrado
confidence            string   opcional    — high | medium | low (default: herda do payload global)
```

## Payload global

```
edition_id    int     OBRIGATÓRIO — ID da edição do torneio no Tennis Hub
source        string  OBRIGATÓRIO — origem: cosat | cbt | fpt | fct | manual
source_url    string  opcional    — URL global da lista de inscritos
confidence    string  opcional    — default: medium
dry_run       bool    opcional    — true = prévia sem salvar (default: false)
entries       array   OBRIGATÓRIO — lista de inscritos (ver colunas acima)
```

## Exemplo JSON completo

```json
{
  "edition_id": 42,
  "source": "cosat",
  "source_url": "https://cosat.tournamentsoftware.com/sport/tournament?id=XXX",
  "confidence": "medium",
  "dry_run": false,
  "entries": [
    {
      "player_name": "João Silva",
      "category_text": "Sub-14 Masculino",
      "player_external_id": "COSAT-001",
      "ranking_position": 5,
      "ranking_source": "COSAT Jan/2026",
      "payment_status": "paid",
      "removed_or_replaced": false,
      "replacement_reason": "",
      "notes": "",
      "source_url": ""
    },
    {
      "player_name": "Ana Costa",
      "category_text": "Sub-14 Feminino",
      "player_external_id": "COSAT-002",
      "ranking_position": 12,
      "ranking_source": "COSAT Jan/2026",
      "payment_status": "paid",
      "removed_or_replaced": true,
      "replacement_reason": "Substituída por atleta de ranking superior após fechamento das vagas.",
      "notes": ""
    }
  ]
}
```

## Exemplo CSV

Salvar como UTF-8. Primeira linha = cabeçalho.

```csv
player_name,category_text,player_external_id,ranking_position,ranking_source,payment_status,removed_or_replaced,replacement_reason,notes
João Silva,Sub-14 Masculino,COSAT-001,5,COSAT Jan/2026,paid,false,,
Ana Costa,Sub-14 Feminino,COSAT-002,12,COSAT Jan/2026,paid,true,Substituída por atleta de ranking superior,
Pedro Lima,Sub-14 Masculino,COSAT-003,,COSAT Jan/2026,unknown,false,,
```

Para importar CSV via n8n: usar nó "Spreadsheet File" → converter em JSON → chamar bulk-import.

## Status possíveis

| `payment_status` | `removed_or_replaced` | Status exibido no app |
|---|---|---|
| `paid` | `false` | Confirmado na chave (se slot ≤ max_vagas) |
| `paid` | `false` | Lista de espera (se slot > max_vagas) |
| `paid` | `true` | **Removido — critério de ranking** |
| `pending` | qualquer | Aguardando pagamento |
| `unknown` | qualquer | Aguardando pagamento |

> **Regra de ouro**: `removed_or_replaced=true` sempre prevalece sobre `payment_status`.

## Regras de duplicidade (dedup)

Chave única: `(edition_id, category_text, player_external_id, source)`

- Se `player_external_id` estiver vazio, o sistema usa `""` como ID.
  Se dois atletas sem external_id forem importados na mesma categoria+source,
  o segundo vai fazer upsert do primeiro (problema!). **Sempre forneça external_id quando disponível.**
- Reimportar com mesmo external_id = atualiza os dados (safe).
- Usar `dry_run=true` antes de confirmar importação em produção.

## Resposta do endpoint

```json
{
  "dry_run": false,
  "edition_id": 42,
  "edition_title": "G1 - Copa Brasil Sub-14",
  "source": "cosat",
  "created": 28,
  "updated": 4,
  "skipped": 0,
  "errors": [
    {"row": 7, "error": "player_name obrigatório.", "data": {...}}
  ],
  "detail": "28 criadas, 4 atualizadas, 0 erros."
}
```

## Como encontrar o edition_id

1. Acesse o painel admin do Tennis Hub: `https://www.tennis.app.br/admin`
2. Ou via API: `GET https://api.tennis.app.br/api/tournaments/editions/?q=nome+do+torneio`
3. O `id` retornado é o `edition_id` para usar no import.

## Como importar dados da COSAT

1. Abra a página pública do torneio em `cosat.tournamentsoftware.com`
2. Localize a lista de inscritos (seção Entry List ou Draw)
3. Selecione e copie a tabela
4. Use n8n com AI Agent para parsear o texto em JSON (ver `docs/integrations/cosat_n8n_pipeline.md`)
5. Execute com `dry_run=true` para revisar
6. Execute com `dry_run=false` para salvar

## Como revisar no mobile

Após importação, abra qualquer torneio → "Ver inscritos".
Verifique:
- Nome do atleta ✓
- Categoria ✓  
- Ranking (se disponível)
- Status (Confirmado / Lista de espera / Removido)
- Fonte: ex. "COSAT"
- Última atualização
- Indicador de confiança
