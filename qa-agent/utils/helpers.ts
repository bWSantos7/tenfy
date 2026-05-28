import { Page, expect } from '@playwright/test';

// ─── Credenciais via env ──────────────────────────────────────────────────────
export const CREDS = {
  responsavel: {
    email: process.env.RESPONSAVEL_EMAIL!,
    password: process.env.RESPONSAVEL_PASSWORD!,
    label: 'Responsável',
  },
  dependente: {
    email: process.env.DEPENDENTE_EMAIL!,
    password: process.env.DEPENDENTE_PASSWORD!,
    label: 'Dependente',
  },
};

export const WEB_URL = process.env.WEB_URL || 'https://www.tennis.app.br';
export const API_URL = process.env.API_URL || 'https://api.tennis.app.br';

// ─── Mapeamento de modalidades ─────────────────────────────────────────────────
export const MODALITY_LABELS: Record<string, string> = {
  tennis: 'Tênis',
  beach_tennis: 'Beach Tennis',
  padel: 'Padel',
  wheelchair: 'Cadeira de rodas',
};

// ─── Login helper ─────────────────────────────────────────────────────────────
export async function login(
  page: Page,
  email: string,
  password: string,
  label = 'Usuário',
): Promise<void> {
  await page.goto('/login');
  await page.waitForLoadState('networkidle');

  await page.locator('[data-testid="login-email"]').fill(email);
  await page.locator('[data-testid="login-password"]').fill(password);
  await page.locator('[data-testid="login-submit"]').click();

  // Aguarda redirecionamento pós-login (URL muda para /inicio ou similar)
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 20_000 });

  console.log(`  ✅ Login realizado: ${label} (${email})`);
}

// ─── Logout helper ────────────────────────────────────────────────────────────
export async function logout(page: Page): Promise<void> {
  // Navega diretamente para /logout ou limpa localStorage
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  await page.goto('/login');
  await page.waitForLoadState('networkidle');
  console.log('  ✅ Logout realizado via limpeza de storage');
}

// ─── Screenshot helper ────────────────────────────────────────────────────────
export async function screenshotStep(
  page: Page,
  name: string,
  step: string,
): Promise<string> {
  const filename = `reports/screenshots/${name}-${step.replace(/[^a-z0-9]/gi, '_')}.png`;
  await page.screenshot({ path: filename, fullPage: true });
  return filename;
}

// ─── Navega para /torneios e aguarda carregamento ─────────────────────────────
export async function goToTournaments(page: Page): Promise<void> {
  await page.goto('/torneios');
  await page.waitForLoadState('networkidle');
  // Aguarda que o spinner desapareça
  await page.waitForSelector('[data-testid="tournament-list"], .card', { timeout: 20_000 });
}

// ─── Abre os filtros avançados ────────────────────────────────────────────────
export async function openFilters(page: Page): Promise<void> {
  const toggle = page.locator('[data-testid="tournaments-filter-toggle"]');
  // Se os filtros ainda não estão visíveis, clica para abrir
  const modalitySelect = page.locator('[data-testid="filter-modality"]');
  if (!(await modalitySelect.isVisible())) {
    await toggle.click();
    await modalitySelect.waitFor({ state: 'visible', timeout: 5_000 });
  }
}

// ─── Seleciona modalidade no filtro ─────────────────────────────────────────
export async function selectModality(page: Page, modality: string): Promise<void> {
  await openFilters(page);
  await page.locator('[data-testid="filter-modality"]').selectOption(modality);
  await page.waitForLoadState('networkidle');
}

// ─── Seleciona UF no filtro ───────────────────────────────────────────────────
export async function selectState(page: Page, state: string): Promise<void> {
  await openFilters(page);
  await page.locator('[data-testid="filter-state"]').selectOption(state);
  await page.waitForLoadState('networkidle');
}

// ─── Coleta modalidades de todos os cards visíveis ────────────────────────────
// Os cards exibem a modalidade como texto ou atributo data-modality
export async function collectVisibleModalities(page: Page): Promise<string[]> {
  // Busca por texto que contenha "Beach Tennis" ou "Tênis" nos cards
  const cards = await page.locator('[data-testid="tournament-list"] [data-modality]').all();
  const modalities: string[] = [];
  for (const card of cards) {
    const m = await card.getAttribute('data-modality');
    if (m) modalities.push(m);
  }
  return modalities;
}

// ─── Coleta UF de todos os cards visíveis ─────────────────────────────────────
export async function collectVisibleStates(page: Page): Promise<string[]> {
  // Extrai texto de venue_state dos cards (busca padrão "CIDADE/UF")
  const cards = await page.locator('[data-testid="tournament-list"] [data-venue-state]').all();
  const states: string[] = [];
  for (const card of cards) {
    const s = await card.getAttribute('data-venue-state');
    if (s) states.push(s);
  }
  return states;
}

// ─── Aguarda que a lista de torneios seja carregada (sem spinner) ─────────────
export async function waitForTournamentList(page: Page): Promise<void> {
  // Aguarda o spinner desaparecer
  await page.waitForFunction(
    () => !document.querySelector('.animate-spin'),
    { timeout: 25_000 },
  );
}

// ─── Verifica se texto de modalidade aparece na lista de cards ────────────────
export async function listContainsModalityText(page: Page, text: string): Promise<boolean> {
  try {
    const list = page.locator('[data-testid="tournament-list"]');
    const content = await list.textContent();
    return content?.includes(text) ?? false;
  } catch {
    return false;
  }
}

// ─── Obtém o primeiro card de torneio e retorna o link para o detalhe ─────────
export async function getFirstTournamentDetailUrl(page: Page): Promise<string | null> {
  const firstCard = page.locator('[data-testid="tournament-list"] a').first();
  if (!(await firstCard.isVisible())) return null;
  return firstCard.getAttribute('href');
}
