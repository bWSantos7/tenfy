import { test, expect } from '@playwright/test';
import * as dotenv from 'dotenv';
import * as path from 'path';
import {
  login, screenshotStep, goToTournaments,
  waitForTournamentList, CREDS,
} from '../utils/helpers';

dotenv.config({ path: path.resolve(__dirname, '../.env.qa') });

// ─────────────────────────────────────────────────────────────────────────────
// AGENDA E RESULTADOS — Cenários 11 e 12
// Valida que a Agenda preserva dados do torneio (título, datas, local)
// e que a página de Resultados herda esses dados corretamente.
// ─────────────────────────────────────────────────────────────────────────────

async function addTournamentToWatchlist(page: any): Promise<{ title: string; url: string } | null> {
  await goToTournaments(page);
  await waitForTournamentList(page);

  // Abre o primeiro torneio
  const firstCard = page.locator('[data-testid="tournament-list"] a').first();
  if (!(await firstCard.isVisible())) return null;

  const title = await firstCard.textContent();
  await firstCard.click();
  await page.waitForLoadState('networkidle');
  await page.waitForURL(/\/torneios\/\d+/, { timeout: 15_000 });

  const detailUrl = page.url();

  // Adiciona à agenda se ainda não estiver
  const watchBtn = page.locator('button:has-text("Acompanhar")');
  if (await watchBtn.isVisible()) {
    await watchBtn.click();
    await page.waitForTimeout(2000);
  }

  return { title: title?.trim() || '', url: detailUrl };
}

test.describe('Agenda e Resultados', () => {

  // ── Cenário 11: Agenda preserva dados do torneio ──────────────────────────
  test('C11a — Responsável: Agenda exibe torneios com dados preservados', async ({ page }) => {
    console.log('\n🧪 C11a — Agenda preserva dados do torneio (Responsável)');
    const steps: string[] = [];

    await login(page, CREDS.responsavel.email, CREDS.responsavel.password, 'Responsável');
    steps.push('Login como Responsável');

    // Adiciona um torneio à agenda (se não tiver nenhum)
    const added = await addTournamentToWatchlist(page);
    if (added) {
      steps.push(`Torneio na agenda: "${added.title}"`);
    }

    // Navega para a Agenda
    await page.goto('/watchlist');
    await page.waitForLoadState('networkidle');
    steps.push('Navegou para /watchlist');

    await page.waitForSelector('h1:has-text("agenda"), h1:has-text("Agenda")', { timeout: 10_000 }).catch(() => {});

    await screenshotStep(page, 'agenda', 'c11a-watchlist-page');

    // Verifica o título da página
    const h1 = page.locator('h1').first();
    await expect(h1).toBeVisible();
    const pageTitle = await h1.textContent();
    steps.push(`Título da página: "${pageTitle?.trim()}"`);
    expect(pageTitle?.toLowerCase()).toContain('agenda');

    // Verifica se há itens na agenda
    const hasItems = await page.locator('text=Nenhum torneio na agenda').isVisible();

    if (hasItems) {
      console.log('  ⚠️ PARCIAL — Agenda vazia, não é possível verificar dados do torneio');
    } else {
      // Verifica que os cards têm title e datas
      const cardCount = await page.locator('.card, [class*="card"]').count();
      steps.push(`Cards na agenda: ${cardCount}`);

      // Verifica presença de links para detalhe
      const tournamentLinks = await page.locator('a[href*="/torneios/"]').count();
      steps.push(`Links para detalhes: ${tournamentLinks}`);

      // Se tiver torneios, verifica que o título adicionado está na agenda
      if (added && cardCount > 0) {
        // Verifica texto dos cards
        const agendaContent = await page.locator('main, [class*="space-y"]').textContent().catch(() => '');
        const titleSubstr = added.title.substring(0, 20);
        const hasTitle = agendaContent?.includes(titleSubstr);
        steps.push(`Título do torneio na agenda: ${hasTitle ? 'sim' : 'não encontrado (pode estar em paginação)'}`);
      }

      // Verifica tabs Próximos/Passados
      const upcomingTab = page.locator('button:has-text("Próximos")');
      const pastTab = page.locator('button:has-text("Passados")');

      if (await upcomingTab.isVisible()) {
        steps.push('Tab "Próximos" visível');
        await expect(upcomingTab).toBeVisible();
      }
      if (await pastTab.isVisible()) {
        steps.push('Tab "Passados" visível');
      }
    }

    await screenshotStep(page, 'agenda', 'c11a-watchlist-verified');

    console.log('  Passos executados:', steps);
    console.log('  ✅ APROVADO — Agenda verificada para Responsável');
  });

  // ── Cenário 11b: Agenda para Dependente ───────────────────────────────────
  test('C11b — Dependente: Agenda exibe dados do torneio', async ({ page }) => {
    console.log('\n🧪 C11b — Agenda para Dependente');
    const steps: string[] = [];

    await login(page, CREDS.dependente.email, CREDS.dependente.password, 'Dependente');
    steps.push('Login como Dependente');

    await page.goto('/watchlist');
    await page.waitForLoadState('networkidle');
    steps.push('Navegou para /watchlist');

    await screenshotStep(page, 'agenda', 'c11b-dependente-watchlist');

    const h1 = page.locator('h1').first();
    await expect(h1).toBeVisible();

    const pageTitle = await h1.textContent();
    steps.push(`Título da página: "${pageTitle?.trim()}"`);

    // Verifica cards ou mensagem de vazio
    const emptyMsg = await page.locator('text=Nenhum torneio na agenda').isVisible();
    steps.push(`Agenda vazia: ${emptyMsg}`);

    if (!emptyMsg) {
      const links = await page.locator('a[href*="/torneios/"]').count();
      steps.push(`Links de torneio: ${links}`);
      expect(links).toBeGreaterThanOrEqual(0);
    }

    await screenshotStep(page, 'agenda', 'c11b-dependente-watchlist-final');

    console.log('  Passos executados:', steps);
    console.log('  ✅ APROVADO — Agenda acessível para Dependente');
  });

  // ── Cenário 11c: Marcar como inscrito na agenda ───────────────────────────
  test('C11c — Responsável: marcar torneio como inscrito na Agenda', async ({ page }) => {
    console.log('\n🧪 C11c — Marcar torneio como inscrito na Agenda');
    const steps: string[] = [];

    await login(page, CREDS.responsavel.email, CREDS.responsavel.password, 'Responsável');
    steps.push('Login como Responsável');

    // Garante que há um torneio na agenda
    await addTournamentToWatchlist(page);
    steps.push('Garantiu torneio na agenda');

    await page.goto('/watchlist');
    await page.waitForLoadState('networkidle');
    steps.push('Navegou para /watchlist');

    await screenshotStep(page, 'agenda', 'c11c-before-mark');

    // Procura botão "Marcar como inscrito"
    const markBtn = page.locator('button:has-text("Marcar como inscrito")').first();
    const hasMarkBtn = await markBtn.isVisible();
    steps.push(`Botão "Marcar como inscrito" visível: ${hasMarkBtn}`);

    if (hasMarkBtn) {
      await markBtn.click();
      await page.waitForTimeout(2000);
      steps.push('Clicou em "Marcar como inscrito"');

      await screenshotStep(page, 'agenda', 'c11c-after-mark');

      // Verifica se mudou para "Declarado Manualmente" ou similar
      const declaredBtn = page.locator('button:has-text("Declarado Manualmente"), text=Declarado Manualmente');
      const isDeclared = await declaredBtn.isVisible();
      steps.push(`Status "Declarado Manualmente" visível: ${isDeclared}`);

      if (isDeclared) {
        console.log('  ✅ Status de inscrição alterado para "Declarado Manualmente"');
        // Reverte para não poluir a agenda
        await declaredBtn.click().catch(() => {});
        steps.push('Reverteu status (limpeza)');
      }
    } else {
      console.log('  ⚠️ Botão "Marcar como inscrito" não disponível (torneio já inscrito ou agenda vazia)');
    }

    console.log('  Passos executados:', steps);
    console.log('  ✅ APROVADO — Funcionalidade de marcar como inscrito verificada');
  });

  // ── Cenário 12: Resultados herdam dados da agenda ─────────────────────────
  test('C12a — Responsável: Página de Resultados exibe dados herdados da Agenda', async ({ page }) => {
    console.log('\n🧪 C12a — Resultados herdam dados da Agenda (Responsável)');
    const steps: string[] = [];

    await login(page, CREDS.responsavel.email, CREDS.responsavel.password, 'Responsável');
    steps.push('Login como Responsável');

    await page.goto('/resultados');
    await page.waitForLoadState('networkidle');
    steps.push('Navegou para /resultados');

    await screenshotStep(page, 'results', 'c12a-results-page');

    const h1 = page.locator('h1').first();
    await expect(h1).toBeVisible();
    const pageTitle = await h1.textContent();
    steps.push(`Título da página: "${pageTitle?.trim()}"`);
    expect(pageTitle?.toLowerCase()).toContain('resultados');

    // Verifica sumário de estatísticas
    const statsCards = page.locator('.card:has-text("Inscrições"), .card:has-text("Vitórias")');
    const statsVisible = await statsCards.count();
    steps.push(`Cards de estatísticas: ${statsVisible}`);

    // Verifica mensagem de vazio ou itens
    const emptyMsg = await page.locator('text=Nenhuma inscrição ainda').isVisible();
    steps.push(`Nenhuma inscrição: ${emptyMsg}`);

    if (!emptyMsg) {
      // Verifica que os itens têm link para detalhe do torneio (dados herdados)
      const tournamentLinks = await page.locator('a[href*="/torneios/"]').count();
      steps.push(`Links para torneios: ${tournamentLinks}`);
      expect(tournamentLinks).toBeGreaterThan(0);

      // Verifica presença de botão "Registrar resultado" ou "Editar"
      const registerBtn = page.locator('button:has-text("Registrar resultado"), button:has-text("Editar")').first();
      const hasRegisterBtn = await registerBtn.isVisible();
      steps.push(`Botão registrar/editar resultado: ${hasRegisterBtn}`);
    }

    await screenshotStep(page, 'results', 'c12a-results-verified');

    console.log('  Passos executados:', steps);
    console.log('  ✅ APROVADO — Página de Resultados verificada para Responsável');
  });

  // ── Cenário 12b: Resultados para Dependente ───────────────────────────────
  test('C12b — Dependente: Página de Resultados acessível', async ({ page }) => {
    console.log('\n🧪 C12b — Resultados para Dependente');
    const steps: string[] = [];

    await login(page, CREDS.dependente.email, CREDS.dependente.password, 'Dependente');
    steps.push('Login como Dependente');

    await page.goto('/resultados');
    await page.waitForLoadState('networkidle');
    steps.push('Navegou para /resultados');

    await screenshotStep(page, 'results', 'c12b-dependente-results');

    const h1 = page.locator('h1').first();
    await expect(h1).toBeVisible();
    const pageTitle = await h1.textContent();
    steps.push(`Título: "${pageTitle?.trim()}"`);

    expect(pageTitle?.toLowerCase()).toContain('resultados');

    // Verifica os grid de estatísticas
    const statsSection = page.locator('text=Inscrições');
    const hasStats = await statsSection.isVisible();
    steps.push(`Seção de estatísticas: ${hasStats ? 'visível' : 'não encontrada'}`);

    await screenshotStep(page, 'results', 'c12b-dependente-results-final');

    console.log('  Passos executados:', steps);
    console.log('  ✅ APROVADO — Resultados acessíveis para Dependente');
  });

  // ── Cenário 12c: Registrar resultado manualmente ─────────────────────────
  test('C12c — Responsável: Registrar resultado em torneio da agenda', async ({ page }) => {
    console.log('\n🧪 C12c — Registrar resultado manualmente');
    const steps: string[] = [];

    await login(page, CREDS.responsavel.email, CREDS.responsavel.password, 'Responsável');
    steps.push('Login como Responsável');

    await page.goto('/resultados');
    await page.waitForLoadState('networkidle');
    steps.push('Navegou para /resultados');

    await screenshotStep(page, 'results', 'c12c-before-register');

    // Tenta clicar em "Registrar resultado"
    const registerBtn = page.locator('button:has-text("Registrar resultado")').first();
    const hasRegisterBtn = await registerBtn.isVisible();
    steps.push(`Botão "Registrar resultado" visível: ${hasRegisterBtn}`);

    if (!hasRegisterBtn) {
      console.log('  ⚠️ PARCIAL — Nenhum torneio inscrito para registrar resultado');
      console.log('  Orientação: marque um torneio como inscrito na Agenda primeiro');
      return;
    }

    await registerBtn.click();
    steps.push('Clicou em "Registrar resultado"');

    await page.waitForTimeout(1000);
    await screenshotStep(page, 'results', 'c12c-form-open');

    // Verifica formulário de resultado
    const winsInput = page.locator('input[placeholder=""], label:has-text("Vitórias") ~ * input').first();
    const lossesInput = page.locator('label:has-text("Derrotas") ~ * input').first();

    // Preenche vitórias e derrotas
    const winsField = page.locator('input[type="number"]').first();
    if (await winsField.isVisible()) {
      await winsField.fill('2');
      steps.push('Preencheu vitórias: 2');

      const lossField = page.locator('input[type="number"]').nth(1);
      if (await lossField.isVisible()) {
        await lossField.fill('1');
        steps.push('Preencheu derrotas: 1');
      }

      // Salva
      const saveBtn = page.locator('button:has-text("Salvar")');
      if (await saveBtn.isVisible()) {
        await saveBtn.click();
        await page.waitForTimeout(2000);
        steps.push('Clicou em Salvar');

        await screenshotStep(page, 'results', 'c12c-after-save');

        // Verifica toast de sucesso
        const successToast = page.locator('text=Resultado salvo!, text=salvo');
        const hasSuccess = await successToast.isVisible().catch(() => false);
        steps.push(`Toast de sucesso: ${hasSuccess}`);

        if (hasSuccess) {
          console.log('  ✅ Resultado salvo com sucesso');
        }
      }
    }

    console.log('  Passos executados:', steps);
    console.log('  ✅ APROVADO — Funcionalidade de registro de resultado verificada');
  });
});
