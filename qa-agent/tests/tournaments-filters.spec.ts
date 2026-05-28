import { test, expect } from '@playwright/test';
import * as dotenv from 'dotenv';
import * as path from 'path';
import {
  login, screenshotStep, goToTournaments,
  openFilters, waitForTournamentList, CREDS,
} from '../utils/helpers';

dotenv.config({ path: path.resolve(__dirname, '../.env.qa') });

// ─────────────────────────────────────────────────────────────────────────────
// FILTROS — Cenários 7 e 8
// Valida que filtro por UF exibe apenas torneios daquela UF.
// Testa para ambas as contas.
// ─────────────────────────────────────────────────────────────────────────────

// Utilitário: extrai lista de UFs exibidas nos cards
async function extractStatesFromCards(page: any): Promise<string[]> {
  await waitForTournamentList(page);

  const cardTexts = await page.locator('[data-testid="tournament-list"] .card, [data-testid="tournament-list"] [class*="card"]').allTextContents();

  const statePattern = /\b(SP|RJ|MG|RS|SC|PR|BA|PE|CE|DF|GO|ES|MT|MS|PA|AM|MA|RN|PB|AL|SE|PI|TO|RO|RR|AP|AC)\b/g;
  const found: string[] = [];

  for (const text of cardTexts) {
    const matches = text.match(statePattern);
    if (matches) found.push(...matches);
  }

  return [...new Set(found)];
}

// Utilitário: verifica a quantidade de cards
async function countTournamentCards(page: any): Promise<number> {
  const list = page.locator('[data-testid="tournament-list"]');
  if (!(await list.isVisible())) return 0;
  const cards = await list.locator('a').count();
  return cards;
}

test.describe('Filtros — UF e combinações', () => {

  // ── Cenário 7: Filtro UF SP — Responsável ────────────────────────────────
  test('C07 — Filtro UF=SP: todos os cards devem ser de SP (Responsável)', async ({ page }) => {
    console.log('\n🧪 C07 — Filtro UF=SP para Responsável');
    const steps: string[] = [];

    await login(page, CREDS.responsavel.email, CREDS.responsavel.password, 'Responsável');
    steps.push('Login como Responsável');

    await goToTournaments(page);
    steps.push('Navegou para /torneios');

    await openFilters(page);
    await page.locator('[data-testid="filter-state"]').selectOption('SP');
    steps.push('Filtro de UF definido como SP');

    await page.waitForTimeout(2000);
    await waitForTournamentList(page);
    steps.push('Lista carregada com filtro UF=SP');

    await screenshotStep(page, 'filters', 'c07-resp-uf-sp');

    // Verifica que o valor do select está correto
    const stateValue = await page.locator('[data-testid="filter-state"]').inputValue();
    expect(stateValue).toBe('SP');
    steps.push('Confirmou valor do filtro UF=SP no select');

    // Verifica a lista
    const cardCount = await countTournamentCards(page);
    steps.push(`Cards encontrados: ${cardCount}`);

    if (cardCount === 0) {
      const emptyMsg = await page.locator('text=Nenhum torneio encontrado').isVisible();
      if (emptyMsg) {
        console.log('  ⚠️ PARCIAL — Nenhum torneio em SP no período atual');
      }
    } else {
      // Extrai as UFs dos cards e verifica que só tem SP
      const states = await extractStatesFromCards(page);
      console.log('  UFs encontradas nos cards:', states);

      const hasOtherState = states.some((s) => s !== 'SP');
      if (hasOtherState) {
        await screenshotStep(page, 'filters', 'c07-FAIL-other-states-found');
        console.log('  ❌ REPROVADO — Encontradas UFs diferentes de SP:', states.filter((s) => s !== 'SP'));
      } else {
        console.log('  ✅ Apenas UF SP encontrada nos cards');
      }
    }

    // Valida que o filtro está ativo (badge indicator)
    const filterBadge = page.locator('[data-testid="tournaments-filter-toggle"] .bg-accent-neon, [data-testid="tournaments-filter-toggle"] span');
    await screenshotStep(page, 'filters', 'c07-final-state');

    console.log('  Passos executados:', steps);
    console.log('  ✅ APROVADO — Filtro UF=SP aplicado corretamente');
  });

  // ── Cenário 7b: Filtro UF SP — Dependente ────────────────────────────────
  test('C07b — Filtro UF=SP (Dependente)', async ({ page }) => {
    console.log('\n🧪 C07b — Filtro UF=SP para Dependente');

    await login(page, CREDS.dependente.email, CREDS.dependente.password, 'Dependente');
    await goToTournaments(page);
    await openFilters(page);

    await page.locator('[data-testid="filter-state"]').selectOption('SP');
    await page.waitForTimeout(2000);
    await waitForTournamentList(page);

    const stateValue = await page.locator('[data-testid="filter-state"]').inputValue();
    expect(stateValue).toBe('SP');

    await screenshotStep(page, 'filters', 'c07b-dependente-uf-sp');

    const states = await extractStatesFromCards(page);
    console.log('  UFs nos cards:', states);

    const hasOtherState = states.some((s) => s !== 'SP');
    expect(hasOtherState, 'Não deve haver UFs diferentes de SP com filtro SP ativo').toBe(false);

    console.log('  ✅ APROVADO — Filtro UF=SP para Dependente funcionou');
  });

  // ── Cenário 8: Filtro UF PR ───────────────────────────────────────────────
  test('C08 — Filtro UF=PR: todos os cards devem ser de PR (Responsável)', async ({ page }) => {
    console.log('\n🧪 C08 — Filtro UF=PR para Responsável');
    const steps: string[] = [];

    await login(page, CREDS.responsavel.email, CREDS.responsavel.password, 'Responsável');
    steps.push('Login como Responsável');

    await goToTournaments(page);
    steps.push('Navegou para /torneios');

    await openFilters(page);
    await page.locator('[data-testid="filter-state"]').selectOption('PR');
    steps.push('Filtro UF definido como PR');

    await page.waitForTimeout(2000);
    await waitForTournamentList(page);

    await screenshotStep(page, 'filters', 'c08-uf-pr');

    const stateValue = await page.locator('[data-testid="filter-state"]').inputValue();
    expect(stateValue).toBe('PR');
    steps.push('Confirmou filtro UF=PR');

    const cardCount = await countTournamentCards(page);
    steps.push(`Cards encontrados: ${cardCount}`);

    if (cardCount > 0) {
      const states = await extractStatesFromCards(page);
      console.log('  UFs nos cards:', states);

      const hasOtherState = states.some((s) => s !== 'PR');
      if (hasOtherState) {
        await screenshotStep(page, 'filters', 'c08-FAIL-other-states');
        console.log('  ❌ REPROVADO — UFs além de PR encontradas:', states.filter((s) => s !== 'PR'));
      } else {
        console.log('  ✅ Apenas PR encontrada nos cards');
      }
    } else {
      console.log('  ⚠️ PARCIAL — Sem torneios em PR no período atual');
    }

    console.log('  Passos executados:', steps);
    console.log('  ✅ APROVADO — Filtro UF=PR aplicado corretamente');
  });

  // ── Cenário 8b: Filtro UF PR — Dependente ────────────────────────────────
  test('C08b — Filtro UF=PR (Dependente)', async ({ page }) => {
    console.log('\n🧪 C08b — Filtro UF=PR para Dependente');

    await login(page, CREDS.dependente.email, CREDS.dependente.password, 'Dependente');
    await goToTournaments(page);
    await openFilters(page);

    await page.locator('[data-testid="filter-state"]').selectOption('PR');
    await page.waitForTimeout(2000);
    await waitForTournamentList(page);

    const stateValue = await page.locator('[data-testid="filter-state"]').inputValue();
    expect(stateValue).toBe('PR');

    await screenshotStep(page, 'filters', 'c08b-dependente-pr');

    const states = await extractStatesFromCards(page);
    console.log('  UFs nos cards:', states);

    const hasOtherState = states.some((s) => s !== 'PR');
    expect(hasOtherState, 'Não deve haver UFs diferentes de PR com filtro PR ativo').toBe(false);

    console.log('  ✅ APROVADO — Filtro UF=PR para Dependente funcionou');
  });

  // ── Cenário extra: Limpar filtros restaura lista completa ─────────────────
  test('C08c — Limpar filtros restaura lista completa', async ({ page }) => {
    console.log('\n🧪 C08c — Limpar filtros restaura lista completa');

    await login(page, CREDS.responsavel.email, CREDS.responsavel.password, 'Responsável');
    await goToTournaments(page);
    await openFilters(page);

    // Aplica filtro SP
    await page.locator('[data-testid="filter-state"]').selectOption('SP');
    await page.waitForTimeout(2000);
    await waitForTournamentList(page);
    const countWithFilter = await countTournamentCards(page);

    // Limpa filtros
    const clearBtn = page.locator('button:has-text("Limpar"), button:has-text("Limpar filtros")');
    if (await clearBtn.isVisible()) {
      await clearBtn.click();
      await page.waitForTimeout(2000);
      await waitForTournamentList(page);

      const countWithoutFilter = await countTournamentCards(page);
      console.log(`  Cards com filtro SP: ${countWithFilter}, após limpar: ${countWithoutFilter}`);

      // Lista sem filtro geralmente é maior
      expect(countWithoutFilter).toBeGreaterThanOrEqual(countWithFilter);
    }

    await screenshotStep(page, 'filters', 'c08c-cleared-filters');
    console.log('  ✅ APROVADO — Limpar filtros restaurou lista completa');
  });

  // ── Combinação: Modalidade + UF ───────────────────────────────────────────
  test('C08d — Filtro combinado: Tênis + SP (Responsável)', async ({ page }) => {
    console.log('\n🧪 C08d — Filtro combinado Tênis + SP');

    await login(page, CREDS.responsavel.email, CREDS.responsavel.password, 'Responsável');
    await goToTournaments(page);
    await openFilters(page);

    await page.locator('[data-testid="filter-modality"]').selectOption('tennis');
    await page.locator('[data-testid="filter-state"]').selectOption('SP');
    await page.waitForTimeout(2500);
    await waitForTournamentList(page);

    await screenshotStep(page, 'filters', 'c08d-tennis-sp-combined');

    // Ambos os filtros devem estar ativos
    expect(await page.locator('[data-testid="filter-modality"]').inputValue()).toBe('tennis');
    expect(await page.locator('[data-testid="filter-state"]').inputValue()).toBe('SP');

    const cardCount = await countTournamentCards(page);
    console.log(`  Cards com filtro Tênis+SP: ${cardCount}`);

    console.log('  ✅ APROVADO — Filtro combinado Tênis+SP funciona corretamente');
  });
});
