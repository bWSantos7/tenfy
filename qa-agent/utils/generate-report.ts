import * as fs from 'fs';
import * as path from 'path';

// ─── Lê o JSON de resultados gerado pelo Playwright ──────────────────────────
const resultsPath = path.resolve(__dirname, '../reports/results.json');

interface TestResult {
  title: string;
  status: 'passed' | 'failed' | 'timedOut' | 'skipped';
  duration: number;
  error?: { message?: string };
}

interface TestSuite {
  title: string;
  specs: Array<{
    title: string;
    tests: TestResult[];
  }>;
}

interface PlaywrightReport {
  suites: TestSuite[];
  stats: {
    expected: number;
    unexpected: number;
    skipped: number;
    duration: number;
  };
}

// Mapeamento de cenário → metadados de relatório
const TEST_METADATA: Record<string, {
  funcionalidade: string;
  perfis: string[];
  impacto: string;
  prioridade: 'Alta' | 'Média' | 'Baixa';
  recomendacao: string;
}> = {
  'C01 — Login como Responsável': {
    funcionalidade: 'Autenticação',
    perfis: ['Responsável'],
    impacto: 'Crítico — Sem login, nenhuma funcionalidade está acessível',
    prioridade: 'Alta',
    recomendacao: 'Verificar configuração de JWT e cookies de sessão',
  },
  'C02 — Login como Dependente': {
    funcionalidade: 'Autenticação',
    perfis: ['Dependente'],
    impacto: 'Crítico — Sem login do dependente, conta não é acessível',
    prioridade: 'Alta',
    recomendacao: 'Verificar se a conta de dependente existe e tem senha correta',
  },
  'C03 — Perfil Tênis: lista não deve conter itens de Beach Tennis': {
    funcionalidade: 'Isolamento de Modalidade',
    perfis: ['Responsável'],
    impacto: 'Alto — Exibir modalidades incorretas gera desinformação',
    prioridade: 'Alta',
    recomendacao: 'Verificar filtro de modalidade na API e no frontend',
  },
  'C04 — Filtro Beach Tennis': {
    funcionalidade: 'Isolamento de Modalidade',
    perfis: ['Responsável'],
    impacto: 'Alto — Vazamento de modalidade compromete UX',
    prioridade: 'Alta',
    recomendacao: 'Revisar query de filtragem no backend (modality field)',
  },
  'C07 — Filtro UF=SP': {
    funcionalidade: 'Filtro por UF',
    perfis: ['Responsável'],
    impacto: 'Alto — Filtro incorreto exibe torneios de outros estados',
    prioridade: 'Alta',
    recomendacao: 'Verificar parâmetro state na API de listagem de torneios',
  },
  'C08 — Filtro UF=PR': {
    funcionalidade: 'Filtro por UF',
    perfis: ['Responsável'],
    impacto: 'Alto — Filtro incorreto exibe torneios de outros estados',
    prioridade: 'Alta',
    recomendacao: 'Verificar parâmetro state na API de listagem de torneios',
  },
  'C09 — Troca de dependente': {
    funcionalidade: 'Troca de Perfil/Dependente',
    perfis: ['Responsável'],
    impacto: 'Médio — Filtros antigos podem exibir dados do perfil anterior',
    prioridade: 'Média',
    recomendacao: 'Garantir que sessionStorage é limpo ao trocar perfil',
  },
};

function statusEmoji(status: string): string {
  if (status === 'passed') return '✅ Aprovado';
  if (status === 'failed') return '❌ Reprovado';
  if (status === 'timedOut') return '⏱️ Timeout';
  return '⚠️ Parcial/Ignorado';
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function generateReport(report: PlaywrightReport): string {
  const now = new Date().toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' });
  const total = report.stats.expected + report.stats.unexpected;
  const passed = report.stats.expected;
  const failed = report.stats.unexpected;
  const skipped = report.stats.skipped;
  const duration = formatDuration(report.stats.duration);

  const passRate = total > 0 ? Math.round((passed / total) * 100) : 0;

  let md = `# 📋 Relatório de Validação QA — Tenfy

> **Gerado em:** ${now}  
> **Ambiente:** https://www.tennis.app.br  
> **API:** https://api.tennis.app.br  

---

## 📊 Sumário Executivo

| Métrica | Valor |
|---|---|
| Total de testes | ${total} |
| ✅ Aprovados | ${passed} |
| ❌ Reprovados | ${failed} |
| ⚠️ Ignorados/Parciais | ${skipped} |
| ⏱️ Tempo total | ${duration} |
| 📈 Taxa de aprovação | **${passRate}%** |

`;

  if (failed > 0) {
    md += `> [!CAUTION]\n> **${failed} teste(s) falharam.** Revise as evidências abaixo e corrija os itens reprovados antes de ir para produção.\n\n`;
  } else {
    md += `> [!NOTE]\n> Todos os testes passaram. O ambiente de produção está validado para os cenários cobertos.\n\n`;
  }

  md += `---\n\n## 🧪 Resultados por Funcionalidade\n\n`;

  // Itera pelas suites de teste
  for (const suite of report.suites || []) {
    for (const spec of suite.specs || []) {
      const testResult = spec.tests?.[0];
      if (!testResult) continue;

      const status = testResult.status;
      const duration = formatDuration(testResult.duration);
      const testTitle = spec.title;

      // Busca metadados
      const meta = Object.entries(TEST_METADATA).find(([key]) => testTitle.includes(key.split(' — ')[0]))?.[1];

      md += `### ${statusEmoji(status)} — ${testTitle}\n\n`;
      md += `| Campo | Detalhe |\n|---|---|\n`;
      md += `| **Funcionalidade** | ${meta?.funcionalidade || 'Geral'} |\n`;
      md += `| **Perfis testados** | ${meta?.perfis?.join(', ') || 'Responsável e Dependente'} |\n`;
      md += `| **Status** | ${statusEmoji(status)} |\n`;
      md += `| **Duração** | ${duration} |\n`;

      if (meta) {
        md += `| **Impacto** | ${meta.impacto} |\n`;
        md += `| **Prioridade** | ${meta.prioridade} |\n`;
        md += `| **Recomendação** | ${meta.recomendacao} |\n`;
      }

      if (status === 'failed' && testResult.error?.message) {
        const errorMsg = testResult.error.message.substring(0, 300);
        md += `\n**Erro encontrado:**\n\`\`\`\n${errorMsg}\n\`\`\`\n`;
      }

      // Links para evidências (screenshots)
      const screenshotDir = path.resolve(__dirname, '../reports/screenshots');
      if (fs.existsSync(screenshotDir)) {
        const prefix = testTitle.replace(/[^a-z0-9]/gi, '_').toLowerCase().substring(0, 10);
        const screenshots = fs.readdirSync(screenshotDir).filter((f) => f.toLowerCase().includes(prefix.substring(0, 5)));
        if (screenshots.length > 0) {
          md += `\n**Evidências (screenshots):**\n`;
          screenshots.slice(0, 3).forEach((s) => {
            md += `- \`reports/screenshots/${s}\`\n`;
          });
        }
      }

      md += '\n---\n\n';
    }
  }

  // Seção de cenários cobertos
  md += `## 📋 Mapeamento de Cenários Obrigatórios\n\n`;
  md += `| # | Cenário | Status |\n|---|---|---|\n`;
  md += `| 1 | Login como responsável | Coberto em \`auth.spec.ts\` |\n`;
  md += `| 2 | Login como dependente | Coberto em \`auth.spec.ts\` |\n`;
  md += `| 3 | Perfil Tênis não exibe Beach Tennis | Coberto em \`tournaments-modality.spec.ts\` |\n`;
  md += `| 4 | Perfil Beach Tennis não exibe Tênis | Coberto em \`tournaments-modality.spec.ts\` |\n`;
  md += `| 5 | Filtro Tênis não vaza Beach Tennis | Coberto em \`tournaments-modality.spec.ts\` |\n`;
  md += `| 6 | Filtro Beach Tennis não vaza Tênis | Coberto em \`tournaments-modality.spec.ts\` |\n`;
  md += `| 7 | Filtro UF SP exibe apenas SP | Coberto em \`tournaments-filters.spec.ts\` |\n`;
  md += `| 8 | Filtro UF PR exibe apenas PR | Coberto em \`tournaments-filters.spec.ts\` |\n`;
  md += `| 9 | Troca de dependente limpa filtros e recalcula | Coberto em \`dependents-switch.spec.ts\` |\n`;
  md += `| 10 | Detalhes do torneio corretos | Coberto em \`tournament-details.spec.ts\` |\n`;
  md += `| 11 | Agenda preserva dados do torneio | Coberto em \`agenda-results.spec.ts\` |\n`;
  md += `| 12 | Resultados herdam dados da agenda | Coberto em \`agenda-results.spec.ts\` |\n`;

  md += `\n---\n\n`;
  md += `## 📁 Artefatos Gerados\n\n`;
  md += `| Tipo | Localização |\n|---|---|\n`;
  md += `| Screenshots | \`reports/screenshots/\` |\n`;
  md += `| Traces Playwright | \`reports/test-results/\` |\n`;
  md += `| Vídeos (falhas) | \`reports/test-results/\` |\n`;
  md += `| Relatório HTML | \`reports/html/index.html\` |\n`;
  md += `| JSON bruto | \`reports/results.json\` |\n`;

  md += `\n---\n\n`;
  md += `*Relatório gerado automaticamente pelo agente QA Tenfy — ${now}*\n`;

  return md;
}

// ─── Main ─────────────────────────────────────────────────────────────────────
(async () => {
  console.log('📝 Gerando relatório de validação...');

  if (!fs.existsSync(resultsPath)) {
    console.log('⚠️  Arquivo reports/results.json não encontrado.');
    console.log('   Execute: npm run qa:prod primeiro para gerar os resultados.');

    // Gera um relatório placeholder
    const placeholder = `# 📋 Relatório de Validação QA — Tenfy

> ⚠️ Nenhum resultado encontrado. Execute \`npm run qa:prod\` para gerar os resultados.

`;
    fs.writeFileSync(path.resolve(__dirname, '../reports/validation-report.md'), placeholder, 'utf-8');
    return;
  }

  const raw = fs.readFileSync(resultsPath, 'utf-8');
  let report: PlaywrightReport;

  try {
    report = JSON.parse(raw);
  } catch (e) {
    console.error('❌ Erro ao parsear results.json:', e);
    process.exit(1);
  }

  const md = generateReport(report);
  const outputPath = path.resolve(__dirname, '../reports/validation-report.md');
  fs.writeFileSync(outputPath, md, 'utf-8');

  console.log(`✅ Relatório gerado em: ${outputPath}`);
  console.log(`   Testes: ${report.stats.expected} aprovados, ${report.stats.unexpected} reprovados`);
})();
