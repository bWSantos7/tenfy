# 🎾 Tenfy QA Agent

Agente de QA automatizado usando **Playwright + TypeScript** para validar fluxos reais no ambiente de produção do Tenfy.

## 📋 Pré-requisitos

- Node.js 18+
- npm 9+

## ⚙️ Setup

```bash
cd qa-agent
npm install
npx playwright install chromium
```

## 🔑 Configuração de Credenciais

O arquivo `.env.qa` já está criado com as credenciais de teste. **Nunca comite este arquivo** (já está no `.gitignore`).

```
WEB_URL=https://www.tennis.app.br
API_URL=https://api.tennis.app.br

RESPONSAVEL_EMAIL=brunowsant15@gmail.com
RESPONSAVEL_PASSWORD=claude123

DEPENDENTE_EMAIL=teste@gmail.com
DEPENDENTE_PASSWORD=claude123
```

## 🚀 Executar todos os testes

```bash
npm run qa:prod
```

Este comando:
1. Executa todos os testes contra produção
2. Salva screenshots em `reports/screenshots/`
3. Salva traces em `reports/test-results/`
4. Gera relatório HTML em `reports/html/`
5. Gera `reports/validation-report.md`

## 🧪 Executar suites individuais

```bash
npm run qa:auth          # Autenticação (login/logout)
npm run qa:modality      # Isolamento de modalidades
npm run qa:filters       # Filtros por UF
npm run qa:dependents    # Troca de dependente/perfil
npm run qa:details       # Detalhes do torneio
npm run qa:agenda        # Agenda e resultados
```

## 📊 Ver relatório HTML

```bash
npm run report
```

## 📁 Estrutura

```
qa-agent/
├── tests/
│   ├── auth.spec.ts                    # Cenários 1-2: Login/Logout
│   ├── tournaments-modality.spec.ts    # Cenários 3-6: Modalidades
│   ├── tournaments-filters.spec.ts     # Cenários 7-8: Filtro UF
│   ├── dependents-switch.spec.ts       # Cenário 9: Troca de perfil
│   ├── tournament-details.spec.ts      # Cenário 10: Detalhes
│   └── agenda-results.spec.ts          # Cenários 11-12: Agenda/Resultados
├── utils/
│   ├── helpers.ts                      # Funções compartilhadas
│   └── generate-report.ts              # Gerador do relatório Markdown
├── reports/
│   ├── screenshots/                    # Screenshots por cenário
│   ├── traces/                         # Traces do Playwright
│   ├── videos/                         # Vídeos em caso de falha
│   └── validation-report.md            # Relatório final gerado
├── .env.qa                             # Credenciais (NÃO COMMITAR)
├── playwright.config.ts
├── package.json
└── tsconfig.json
```

## 🎯 Cenários Cobertos

| # | Cenário | Spec |
|---|---------|------|
| 1 | Login como responsável | `auth.spec.ts` |
| 2 | Login como dependente | `auth.spec.ts` |
| 3 | Perfil Tênis não exibe Beach Tennis | `tournaments-modality.spec.ts` |
| 4 | Perfil Beach Tennis não exibe Tênis | `tournaments-modality.spec.ts` |
| 5 | Filtro Tênis não vaza Beach Tennis | `tournaments-modality.spec.ts` |
| 6 | Filtro Beach Tennis não vaza Tênis | `tournaments-modality.spec.ts` |
| 7 | Filtro UF SP exibe apenas SP | `tournaments-filters.spec.ts` |
| 8 | Filtro UF PR exibe apenas PR | `tournaments-filters.spec.ts` |
| 9 | Troca de dependente limpa filtros | `dependents-switch.spec.ts` |
| 10 | Detalhes do torneio corretos | `tournament-details.spec.ts` |
| 11 | Agenda preserva dados do torneio | `agenda-results.spec.ts` |
| 12 | Resultados herdam dados da agenda | `agenda-results.spec.ts` |

## 📋 Relatório

Após execução, o relatório `reports/validation-report.md` contém para cada teste:
- Funcionalidade testada
- Perfis usados (Responsável / Dependente)
- Status: Aprovado / Reprovado / Parcial
- Passos executados
- Resultado esperado vs obtido
- Links para evidências (screenshots, traces)
- Impacto e Prioridade
- Recomendação técnica
