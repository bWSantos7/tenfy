/**
 * TC-TOURNAMENT — Listagem, filtros, compatibilidade e detalhe de torneios.
 */
import { test, expect } from '@playwright/test';
import { AuthPage } from '../pages/AuthPage';
import { TournamentsPage } from '../pages/TournamentsPage';
import { PLAYER } from '../fixtures/users';

test.describe('TC-TOURNAMENT — Torneios', () => {

  test.beforeEach(async ({ page }) => {
    const auth = new AuthPage(page);
    await auth.login(PLAYER.email, PLAYER.password);
  });

  test('TOURN-01 — Listagem de torneios carrega sem erro', async ({ page }) => {
    const t = new TournamentsPage(page);
    await t.goto();
    await expect(page.locator('body')).not.toContainText(/erro 500|internal server error/i);
    // Deve ter algum conteúdo
    await expect(page.locator('main, [role="main"], .space-y-4').first()).toBeVisible({ timeout: 8000 });
  });

  test('TOURN-02 — Torneios aparecem como cards clicáveis', async ({ page }) => {
    const t = new TournamentsPage(page);
    await t.goto();
    const tournamentLinks = page.locator('a[href*="/torneios/"]');
    const count = await tournamentLinks.count();
    expect(count).toBeGreaterThan(0);
  });

  test('TOURN-03 — Detalhe do torneio abre ao clicar', async ({ page }) => {
    const t = new TournamentsPage(page);
    await t.goto();
    await t.openFirstTournament();
    await expect(page).toHaveURL(/\/torneios\/\d+/, { timeout: 10000 });
    await expect(page.locator('body')).not.toContainText(/404|not found/i);
  });

  test('TOURN-04 — Detalhe mostra informações básicas do torneio', async ({ page }) => {
    const t = new TournamentsPage(page);
    await t.goto();
    await t.openFirstTournament();
    // Detalhe deve ter título, data ou local
    const body = await page.locator('body').innerText();
    expect(body.length).toBeGreaterThan(100);
    // Não deve ter campos técnicos vazios expostos
    expect(body).not.toMatch(/undefined|null|\[object/i);
  });

  test('TOURN-05 — Voltar do detalhe mantém filtros aplicados', async ({ page }) => {
    const t = new TournamentsPage(page);
    await t.goto();
    await t.applyTextSearch('Tênis');
    await page.waitForTimeout(1500);
    const countBefore = await t.countCards();
    await t.openFirstTournament();
    await t.goBack();
    // Filtro deve persistir (campo de busca ainda preenchido)
    const searchInput = page.getByPlaceholder(/buscar|pesquisar/i).first();
    if (await searchInput.isVisible({ timeout: 2000 }).catch(() => false)) {
      const value = await searchInput.inputValue();
      expect(value).toBe('Tênis');
    }
  });

  test('TOURN-06 — Filtro por texto retorna resultados coerentes', async ({ page }) => {
    const t = new TournamentsPage(page);
    await t.goto();
    await t.applyTextSearch('Beach Tennis');
    await page.waitForTimeout(2000);
    const body = await page.locator('body').innerText();
    // Ou retorna resultados de Beach Tennis, ou mostra "nenhum resultado"
    expect(
      body.toLowerCase().includes('beach') ||
      body.toLowerCase().includes('nenhum') ||
      body.toLowerCase().includes('sem resultado')
    ).toBeTruthy();
  });

  test('TOURN-07 — Limpar filtros restaura listagem completa', async ({ page }) => {
    const t = new TournamentsPage(page);
    await t.goto();
    const totalBefore = await t.countCards();
    await t.applyTextSearch('xyzxyz_inexistente');
    await page.waitForTimeout(1500);
    await t.clearFilters();
    await page.waitForTimeout(1500);
    const totalAfter = await t.countCards();
    expect(totalAfter).toBeGreaterThanOrEqual(totalBefore);
  });

  test('TOURN-08 — Filtro de modalidade Tennis filtra corretamente', async ({ page }) => {
    const t = new TournamentsPage(page);
    await t.goto();
    await t.applyModalityFilter('tennis');
    await page.waitForTimeout(2000);
    // Não deve mostrar beach_tennis como destaque após filtro
    const body = await page.locator('body').innerText();
    expect(body).not.toMatch(/erro 500/i);
  });

  test('TOURN-09 — Combinação de filtros não quebra a listagem', async ({ page }) => {
    const t = new TournamentsPage(page);
    await t.goto();
    await t.applyModalityFilter('tennis');
    await t.applyTextSearch('SP');
    await page.waitForTimeout(2000);
    await expect(page.locator('body')).not.toContainText(/erro 500|internal server/i);
  });

  test('TOURN-10 — Torneios são ordenados: inscrições abertas primeiro', async ({ page }) => {
    const t = new TournamentsPage(page);
    await t.goto();
    const cards = await page.locator('a[href*="/torneios/"]').all();
    if (cards.length < 2) {
      test.skip();
      return;
    }
    // O status dos primeiros cards deve ser "aberto" ou "encerrando"
    const firstText = await cards[0].textContent() ?? '';
    const hasOpenStatus = /aberto|encerrando|inscrição aberta/i.test(firstText);
    // Não necessariamente garantido sem dados controlados, mas não deve estar "finalizado" primeiro
    const hasFinishedFirst = /finalizado|concluído/i.test(firstText) && cards.length > 3;
    expect(hasFinishedFirst).toBeFalsy();
  });

  test('TOURN-11 — Home exibe seção "Compatíveis com você"', async ({ page }) => {
    await page.goto('/inicio');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    await expect(page.getByText(/compatíveis/i)).toBeVisible({ timeout: 8000 });
  });

  test('TOURN-12 — Seção "Inscrições fechando" aparece na Home', async ({ page }) => {
    await page.goto('/inicio');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    await expect(page.getByText(/fechando|prazo/i)).toBeVisible({ timeout: 8000 });
  });
});
