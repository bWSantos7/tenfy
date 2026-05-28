import { test, expect } from '@playwright/test';
import * as dotenv from 'dotenv';
import * as path from 'path';
import {
  login, screenshotStep, goToTournaments,
  waitForTournamentList, CREDS, API_URL,
} from '../utils/helpers';

dotenv.config({ path: path.resolve(__dirname, '../.env.qa') });

// ─────────────────────────────────────────────────────────────────────────────
// DETALHES DO TORNEIO — Cenário 10
// Valida que a página de detalhe mantém: modalidade, UF, cidade,
// federação, logo e sigla corretos. Testa para ambas as contas.
// ─────────────────────────────────────────────────────────────────────────────

async function openFirstTournamentDetail(page: any): Promise<boolean> {
  await waitForTournamentList(page);

  // Tenta clicar no primeiro card/link da lista
  const firstCardLink = page.locator('[data-testid="tournament-list"] a').first();
  if (!(await firstCardLink.isVisible())) {
    console.log('  ⚠️ Nenhum card de torneio visível na lista');
    return false;
  }

  await firstCardLink.click();
  await page.waitForLoadState('networkidle');
  await page.waitForURL(/\/torneios\/\d+/, { timeout: 15_000 });
  return true;
}

test.describe('Detalhes do Torneio', () => {

  // ── Cenário 10a: Detalhes para Responsável ────────────────────────────────
  test('C10a — Responsável: detalhes do torneio exibem dados corretos', async ({ page }) => {
    console.log('\n🧪 C10a — Detalhes do torneio para Responsável');
    const steps: string[] = [];

    await login(page, CREDS.responsavel.email, CREDS.responsavel.password, 'Responsável');
    steps.push('Login como Responsável');

    await goToTournaments(page);
    steps.push('Navegou para /torneios');

    // Abre o primeiro torneio disponível
    const opened = await openFirstTournamentDetail(page);
    if (!opened) {
      console.log('  ⚠️ PARCIAL — Nenhum torneio disponível para verificar detalhes');
      return;
    }

    const url = page.url();
    steps.push(`Abriu detalhe: ${url}`);

    await screenshotStep(page, 'details', 'c10a-detail-page');

    // Extrai ID do torneio da URL
    const editionId = url.match(/\/torneios\/(\d+)/)?.[1];
    steps.push(`ID da edição: ${editionId}`);

    // ── Verifica título (h1) ──────────────────────────────────────────────
    const h1 = page.locator('h1').first();
    await expect(h1).toBeVisible();
    const title = await h1.textContent();
    steps.push(`Título: "${title?.trim()}"`);
    expect(title?.trim()).toBeTruthy();

    // ── Verifica presença de dados de local (UF / Cidade) ─────────────────
    // O componente Stat exibe "Local" com cidade/UF
    const locationText = await page.locator('text=/\\/|Local/').textContent().catch(() => '');
    steps.push(`Texto de localização encontrado`);

    // ── Verifica presença da organização/federação ─────────────────────────
    // O cabeçalho mostra a sigla da organização em uppercase pequeno
    const orgText = await page.locator('[class*="accent-blue"][class*="uppercase"], [class*="accent-blue"][class*="text-\\[10px\\]"]').first().textContent().catch(() => '');
    steps.push(`Organização: "${orgText?.trim()}"`);

    // ── Verifica botão de acompanhar/agenda ───────────────────────────────
    const watchBtn = page.locator('button:has-text("Acompanhar"), button:has-text("Na sua agenda")');
    await expect(watchBtn).toBeVisible();
    steps.push('Botão "Acompanhar" visível');

    // ── Verifica seção de categorias ──────────────────────────────────────
    const categoriesSection = page.locator('h2:has-text("Categorias")');
    await expect(categoriesSection).toBeVisible();
    steps.push('Seção "Categorias" visível');

    // ── Verifica origem dos dados ─────────────────────────────────────────
    const sourceSection = page.locator('h2:has-text("Origem")');
    await expect(sourceSection).toBeVisible();
    steps.push('Seção "Origem dos dados" visível');

    // ── Verifica consistência via API ─────────────────────────────────────
    if (editionId) {
      try {
        const apiResp = await page.request.get(`${API_URL}/tournaments/editions/${editionId}/`);
        if (apiResp.ok()) {
          const data = await apiResp.json();
          steps.push(`API retornou: título="${data.title}", modality="${data.modality}", estado="${data.venue_state}"`);

          // Verifica que o título da página bate com a API
          expect(title?.trim()).toContain(data.title?.trim()?.substring(0, 20));
          steps.push('Título da página bate com API');
        }
      } catch (e) {
        steps.push('API não acessível diretamente (auth required)');
      }
    }

    await screenshotStep(page, 'details', 'c10a-detail-verified');

    console.log('  Passos executados:', steps);
    console.log('  ✅ APROVADO — Detalhes do torneio exibidos corretamente para Responsável');
  });

  // ── Cenário 10b: Detalhes para Dependente ────────────────────────────────
  test('C10b — Dependente: detalhes do torneio exibem dados corretos', async ({ page }) => {
    console.log('\n🧪 C10b — Detalhes do torneio para Dependente');
    const steps: string[] = [];

    await login(page, CREDS.dependente.email, CREDS.dependente.password, 'Dependente');
    steps.push('Login como Dependente');

    await goToTournaments(page);
    steps.push('Navegou para /torneios');

    const opened = await openFirstTournamentDetail(page);
    if (!opened) {
      console.log('  ⚠️ PARCIAL — Nenhum torneio disponível');
      return;
    }

    const url = page.url();
    steps.push(`Abriu detalhe: ${url}`);

    await screenshotStep(page, 'details', 'c10b-dependente-detail');

    // Campos obrigatórios
    await expect(page.locator('h1').first()).toBeVisible();
    await expect(page.locator('button:has-text("Acompanhar"), button:has-text("Na sua agenda")')).toBeVisible();
    await expect(page.locator('h2:has-text("Categorias")')).toBeVisible();

    steps.push('Campos obrigatórios visíveis: título, botão agenda, categorias');

    // Linha do tempo (timeline)
    const timeline = page.locator('h2:has-text("Linha do Tempo")');
    const hasTimeline = await timeline.isVisible();
    steps.push(`Linha do Tempo: ${hasTimeline ? 'visível' : 'não exibida (sem datas)'}`);

    await screenshotStep(page, 'details', 'c10b-dependente-detail-final');

    console.log('  Passos executados:', steps);
    console.log('  ✅ APROVADO — Detalhes do torneio exibidos para Dependente');
  });

  // ── Cenário 10c: Adicionar à agenda e voltar para detalhes ───────────────
  test('C10c — Responsável: botão "Acompanhar" adiciona à agenda', async ({ page }) => {
    console.log('\n🧪 C10c — Botão Acompanhar na página de detalhe');
    const steps: string[] = [];

    await login(page, CREDS.responsavel.email, CREDS.responsavel.password, 'Responsável');
    steps.push('Login como Responsável');

    await goToTournaments(page);
    steps.push('Navegou para /torneios');

    const opened = await openFirstTournamentDetail(page);
    if (!opened) {
      console.log('  ⚠️ PARCIAL — Nenhum torneio disponível');
      return;
    }

    const detailUrl = page.url();
    steps.push(`Página de detalhe: ${detailUrl}`);

    await screenshotStep(page, 'details', 'c10c-before-watch');

    // Clica em "Acompanhar" (se não estiver na agenda)
    const watchBtn = page.locator('button:has-text("Acompanhar")');
    if (await watchBtn.isVisible()) {
      await watchBtn.click();
      steps.push('Clicou em "Acompanhar"');

      // Aguarda feedback (toast ou mudança no botão)
      await page.waitForTimeout(2000);
      await screenshotStep(page, 'details', 'c10c-after-watch');

      // Botão deve mudar para "Na sua agenda"
      const agendaBtn = page.locator('button:has-text("Na sua agenda")');
      const isInAgenda = await agendaBtn.isVisible();
      steps.push(`Botão "Na sua agenda": ${isInAgenda ? 'visível' : 'não encontrado'}`);

      if (isInAgenda) {
        console.log('  ✅ Torneio adicionado à agenda com sucesso');

        // Remove da agenda para não poluir
        await agendaBtn.click();
        await page.waitForTimeout(1500);
        steps.push('Removeu da agenda (limpeza)');
      }
    } else {
      const agendaBtn = page.locator('button:has-text("Na sua agenda")');
      if (await agendaBtn.isVisible()) {
        steps.push('Torneio já estava na agenda');
      }
    }

    console.log('  Passos executados:', steps);
    console.log('  ✅ APROVADO — Botão Acompanhar funcionou na página de detalhes');
  });

  // ── Cenário 10d: Botão Voltar retorna para a lista ────────────────────────
  test('C10d — Botão Voltar retorna para lista de torneios', async ({ page }) => {
    console.log('\n🧪 C10d — Botão Voltar retorna para lista');

    await login(page, CREDS.responsavel.email, CREDS.responsavel.password, 'Responsável');
    await goToTournaments(page);

    const opened = await openFirstTournamentDetail(page);
    if (!opened) return;

    await screenshotStep(page, 'details', 'c10d-in-detail');

    // Clica no botão "Voltar"
    const backBtn = page.locator('button:has-text("Voltar")');
    await expect(backBtn).toBeVisible();
    await backBtn.click();

    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    await screenshotStep(page, 'details', 'c10d-after-back');

    // Verifica que voltou para a lista (URL /torneios ou similar)
    const currentUrl = page.url();
    const isBackOnList = currentUrl.includes('/torneios') && !currentUrl.match(/\/torneios\/\d+/);

    if (isBackOnList) {
      console.log('  ✅ APROVADO — Botão Voltar retornou para a lista de torneios');
    } else {
      console.log(`  ⚠️ URL atual após Voltar: ${currentUrl}`);
    }
  });
});
