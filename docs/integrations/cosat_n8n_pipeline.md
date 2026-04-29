# Pipeline COSAT/COSANT → Tennis Hub via n8n

## 1. Objetivo

Trazer dados reais de torneios e inscritos da COSAT (Confederación Sudamericana de Tenis)
para o Tennis Hub sem parceria oficial de API, usando importação assistida via n8n.

**Por que não é automático?**  
O site `cosat.tournamentsoftware.com` bloqueia crawling em `robots.txt` (disallows `/sport/`, `/tournament/`, `/ranking/`).
A API usada anteriormente retorna HTTP 404. A solução é um pipeline semi-automático onde
um operador captura os dados publicamente visíveis e n8n os normaliza e importa para o backend.

---

## 2. Visão geral do pipeline

```
[COSAT site público]
       │
       ▼ (operador captura manualmente ou n8n usa HTTP Request)
[n8n — entrada de dados]
  ├── URL da página de torneio
  ├── HTML copiado
  ├── CSV/Excel exportado
  └── Texto colado
       │
       ▼
[n8n — normalização]
  ├── HTML Extract (parse tabela de inscritos)
  ├── Code node (mapeia campos → schema Tennis Hub)
  └── AI Agent (LLM parser para texto não estruturado)
       │
       ▼
[n8n — validação]
  ├── Verificar campos obrigatórios
  ├── Calcular confidence
  └── dry_run=true → preview
       │
       ▼
[Tennis Hub API — POST /api/registrations/federation/bulk-import/]
  ├── Auth: header X-Import-Token
  └── Dados persistidos em FederationEntry com source_url + synced_at
       │
       ▼
[Mobile — RegistrationListScreen]
  └── Exibe: nome, ranking, status, fonte, última sincronização
```

---

## 3. Formas de entrada suportadas

### A) URL da página do torneio
n8n faz HTTP Request à URL pública do torneio e extrai HTML com o nó "HTML Extract".
Use somente para URLs que não são bloqueadas por robots.txt.

### B) HTML colado pelo admin
Admin copia o HTML/texto da página de inscritos e cola em campo do n8n (Manual Trigger com formulário).

### C) CSV / Excel
Admin exporta lista de inscritos em CSV ou Excel e faz upload para n8n.
n8n usa nó "Spreadsheet File" para ler e normalizar.

### D) Texto copiado
Admin copia o texto da tabela de inscritos e passa para um AI Agent (GPT/Claude) que
estrutura os dados no schema esperado.

### E) JSON normalizado externo
Qualquer ferramenta externa (Python script, Playwright, Puppeteer) pode chamar
diretamente o endpoint `/api/registrations/federation/bulk-import/` com o JSON correto.

---

## 4. Nós do fluxo n8n recomendado

### Fluxo principal (entrada via HTML/CSV)

```
[Manual Trigger]
  └── Formulário: edition_id, source_url, tipo de entrada (HTML/CSV/texto)
       │
       ▼
[Switch — tipo de entrada]
  ├── HTML → [HTTP Request] + [HTML Extract]
  ├── CSV  → [Spreadsheet File]
  └── text → [AI Agent node (LLM parser)]
       │
       ▼
[Code node — normalizar para schema Tennis Hub]
       │
       ▼
[IF — campos obrigatórios OK?]
  ├── SIM → [HTTP Request — POST bulk-import com dry_run=true]
  │           └── [Manual review checkpoint]
  │                └── [HTTP Request — POST bulk-import com dry_run=false]
  └── NÃO → [Error Trigger — notificar operador]
```

### Fluxo agendado (tentativa automática para fontes permitidas)

```
[Cron — ex: toda segunda às 7h]
       │
       ▼
[HTTP Request — buscar lista de URLs de torneios ativos]
  └── GET /api/tournaments/editions/?status=open&circuit=COSAT
       │
       ▼
[Loop — para cada torneio]
       │
       ▼
[HTTP Request — tentar URL pública do torneio COSAT]
  └── Se 403/block → pular + notificar operador
       │
       ▼
[HTML Extract ou AI Agent]
       │
       ▼
[Code — normalizar]
       │
       ▼
[HTTP Request — POST bulk-import]
```

---

## 5. Payload esperado pelo endpoint

**Endpoint:** `POST https://api.tennis.app.br/api/registrations/federation/bulk-import/`

**Autenticação:** Header `X-Import-Token: <IMPORT_API_TOKEN>`  
O token é configurado na variável de ambiente `IMPORT_API_TOKEN` no Railway.

### Payload completo

```json
{
  "edition_id": 42,
  "source": "cosat",
  "source_url": "https://cosat.tournamentsoftware.com/sport/tournament?id=XXXX",
  "confidence": "medium",
  "dry_run": false,
  "entries": [
    {
      "player_name": "João Silva",
      "category_text": "Sub-14 Masculino",
      "player_external_id": "COSAT-12345",
      "ranking_position": 8,
      "ranking_source": "COSAT Jan/2026",
      "payment_status": "paid",
      "removed_or_replaced": false,
      "replacement_reason": "",
      "notes": "",
      "source_url": "https://cosat.tournamentsoftware.com/sport/draw?id=XXXX"
    },
    {
      "player_name": "Pedro Oliveira",
      "category_text": "Sub-14 Masculino",
      "player_external_id": "COSAT-99887",
      "ranking_position": 35,
      "ranking_source": "COSAT Jan/2026",
      "payment_status": "paid",
      "removed_or_replaced": true,
      "replacement_reason": "Substituído por atleta de ranking superior após fechamento das vagas.",
      "notes": "",
      "source_url": ""
    }
  ]
}
```

### Campos obrigatórios

| Campo | Tipo | Descrição |
|---|---|---|
| `edition_id` | int | ID da TournamentEdition no Tennis Hub |
| `source` | string | Origem: `cosat`, `cbt`, `fpt`, `manual`, etc. |
| `entries[].player_name` | string | Nome do atleta |
| `entries[].category_text` | string | Categoria exata conforme publicada |

### Campos opcionais

| Campo | Tipo | Default | Descrição |
|---|---|---|---|
| `source_url` | string | `""` | URL da página de origem |
| `confidence` | string | `medium` | `high`, `medium`, `low` |
| `dry_run` | bool | `false` | `true` = prévia sem salvar |
| `entries[].player_external_id` | string | `""` | ID do atleta na federação (dedup key) |
| `entries[].ranking_position` | int | null | Posição no ranking (menor = melhor) |
| `entries[].ranking_source` | string | `""` | Ex: "COSAT Jan/2026" |
| `entries[].payment_status` | string | `unknown` | `paid`, `pending`, `unknown` |
| `entries[].removed_or_replaced` | bool | `false` | Removido por regra de ranking |
| `entries[].replacement_reason` | string | `""` | Motivo da remoção |

### Resposta

```json
{
  "dry_run": false,
  "edition_id": 42,
  "edition_title": "G1 - Copa Brasil Sub-14",
  "source": "cosat",
  "created": 28,
  "updated": 4,
  "skipped": 0,
  "errors": [],
  "detail": "28 criadas, 4 atualizadas, 0 erros."
}
```

---

## 6. Autenticação no n8n

No nó HTTP Request do n8n:

- Method: `POST`
- URL: `https://api.tennis.app.br/api/registrations/federation/bulk-import/`
- Authentication: None (usar header manual)
- Headers:
  ```
  Content-Type: application/json
  X-Import-Token: {{ $env.TENNIS_HUB_IMPORT_TOKEN }}
  ```
- Body: JSON com o payload acima

> Configure `TENNIS_HUB_IMPORT_TOKEN` nas variáveis de ambiente do n8n.
> Gere o token com: `python -c "import secrets; print(secrets.token_hex(32))"`
> Configure o mesmo valor em `IMPORT_API_TOKEN` no Railway.

---

## 7. Mapeamento de campos — HTML da COSAT

Quando o admin cola HTML de uma página COSAT, use o nó HTML Extract com estes seletores
(variam conforme versão do site — ajustar conforme necessário):

```json
{
  "entries": {
    "selector": "table.entry-list tr[data-row]",
    "type": "html"
  }
}
```

Após extrair, use um Code node para mapear:

```javascript
const raw = $input.all();
return raw.map((row, i) => ({
  json: {
    player_name: row.json.playerName?.trim() || row.json['Atleta']?.trim() || '',
    category_text: row.json.category?.trim() || row.json['Categoria']?.trim() || '',
    player_external_id: row.json.id?.toString() || '',
    ranking_position: parseInt(row.json.ranking) || null,
    ranking_source: 'COSAT',
    payment_status: row.json.payment === 'Pago' ? 'paid' : row.json.payment === 'Pendente' ? 'pending' : 'unknown',
    removed_or_replaced: row.json.status?.toLowerCase().includes('substituído') || false,
    replacement_reason: row.json.status?.toLowerCase().includes('substituído')
      ? 'Substituído por atleta de ranking superior.'
      : '',
  }
}));
```

---

## 8. Mapeamento de CSV

Formato esperado do CSV para importação direta:

```csv
player_name,category_text,player_external_id,ranking_position,ranking_source,payment_status,removed_or_replaced,replacement_reason,notes
João Silva,Sub-14 Masculino,COSAT-12345,8,COSAT Jan/2026,paid,false,,
Pedro Oliveira,Sub-14 Masculino,COSAT-99887,35,COSAT Jan/2026,paid,true,Substituído por ranking superior,
```

Use o nó "Spreadsheet File" no n8n para ler e converter em JSON.

---

## 9. Calcular confidence

| Situação | Confidence |
|---|---|
| Dados copiados de API oficial com autenticação | `high` |
| Dados extraídos de página pública HTML (admin revisa) | `medium` |
| Dados inferidos de texto não estruturado (AI parser) | `low` |
| Dados inseridos manualmente pelo admin | `high` |

---

## 10. Evitar duplicidade

O dedup usa: `(edition_id, category_text, player_external_id, source)`.

- Se `player_external_id` estiver em branco, cada nome diferente cria um registro novo.
- Se importar o mesmo atleta duas vezes com o mesmo `player_external_id`, os dados são atualizados (upsert).
- Use `dry_run=true` para verificar quantos seriam criados/atualizados antes de confirmar.

---

## 11. Dados ausentes — como tratar

| Campo ausente | Comportamento |
|---|---|
| `ranking_position` | Salvo como `null`. Exibido como "—" no app. |
| `payment_status` | Default `unknown`. Exibido como "Não informado". |
| `removed_or_replaced` | Default `false`. Atleta aparece como normal. |
| `player_external_id` | Dedup por nome + categoria + source. Risco de duplicata. |

---

## 12. Diferenciação de status

| Condição | Status exibido |
|---|---|
| `removed_or_replaced=true` | Removido — critério de ranking |
| `payment=paid` + `slot <= max_vagas` | Confirmado na chave |
| `payment=paid` + `slot > max_vagas` | Lista de espera |
| `payment=pending` ou `unknown` | Aguardando pagamento |

> **Regra fundamental:** `removed_or_replaced=true` prevalece sobre `payment_status=paid`.
> Um atleta pago pode ser removido se a federação aplicar corte por ranking.

---

## 13. Revisão antes de publicar

1. Montar payload
2. Enviar com `dry_run=true`
3. Revisar `previews` retornados
4. Confirmar com `dry_run=false`

Ou via Django Admin: criar `FederationEntry` manualmente para cada atleta.

---

## 14. Agendamento

Para fontes que permitem acesso automático (CBT API pública, FPT calendário), o n8n pode rodar por cron.
Para COSAT, use Manual Trigger até obter permissão oficial.

---

## 15. Exibição no mobile

Após importação, o app mostra na tela `RegistrationListScreen`:

- Nome do atleta
- Categoria  
- Ranking (se disponível)
- Status: Confirmado / Lista de espera / Aguardando / Removido
- Pagamento
- Fonte: "CBT", "COSAT", "Importação manual"
- Última atualização (synced_at)
- Indicador de confiança (alta / média / baixa)
- Link para fonte original (se source_url disponível)

---

## 16. Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Dados desatualizados | Sempre exibir `synced_at`. Exibir aviso se > 24h. |
| Dados incorretos por erro de parse | Usar `confidence=low` + revisão humana antes de publicar |
| Importação duplicada | Usar `dry_run=true` antes de confirmar |
| Token vaza | Rotacionar `IMPORT_API_TOKEN` no Railway. Nunca expor no app. |
| Mudança de estrutura do site | Pipeline n8n retorna erro → operador revisita manualmente |

---

## 17. Checklist operacional

- [ ] Gerar `IMPORT_API_TOKEN` e configurar no Railway
- [ ] Configurar `TENNIS_HUB_IMPORT_TOKEN` nas variáveis do n8n
- [ ] Localizar edition_id do torneio no painel admin do Tennis Hub
- [ ] Capturar dados do torneio COSAT (HTML / CSV / texto)
- [ ] Executar fluxo n8n com `dry_run=true`
- [ ] Revisar preview (quantos seriam criados/atualizados)
- [ ] Executar com `dry_run=false`
- [ ] Verificar no app mobile (RegistrationListScreen)
- [ ] Confirmar `synced_at` e `source_label` exibidos corretamente
