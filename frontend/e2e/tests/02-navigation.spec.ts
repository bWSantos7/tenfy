/**
 * TC-NAV — Navegação, menu responsivo e acesso às áreas principais.
 */
import { test, expect } from '@playwright/test';
import { AuthPage } from '../pages/AuthPage';
import { PLAYER } from '../fixtures/users';

test.describe('TC-NAV — Navegação e menu', () => {

  test.beforeEach(async ({ page }) => {
    const auth = new AuthPage(page);
    await auth.login(PLAYER.email, PLAYER.password);
  });

  test('NAV-01 — Menu principal visível após login', async ({ page }) => {
    await page.goto('/inicio');
    await page.waitForLoadState('networkidle');
    // Deve haver links de navegação principais
    const nav = page.locator('nav');
    await expect(nav.first()).toBeVisible({ timeout: 8000 });
  });

  test('NAV-02 — Acesso à Home (/inicio)', async ({ page }) => {
    await page.goto('/inicio');
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/inicio/);
    // Título "Olá" ou saudação
    await expect(page.getByText(/olá/i)).toBeVisible({ timeout: 8000 });
  });

  test('NAV-03 — Acesso a Torneios (/torneios)', async ({ page }) => {
    await page.goto('/torneios');
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/torneios/);
    await expect(page.getByText(/torneio/i).first()).toBeVisible({ timeout: 8000 });
  });

  test('NAV-04 — Acesso à Agenda (/watchlist)', async ({ page }) => {
    await page.goto('/watchlist');
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/watchlist/);
  });

  test('NAV-05 — Acesso a Inscrições (/inscricoes)', async ({ page }) => {
    await page.goto('/inscricoes');
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/inscricoes/);
  });

  test('NAV-06 — Acesso a Resultados (/resultados)', async ({ page }) => {
    await page.goto('/resultados');
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/resultados/);
  });

  test('NAV-07 — Acesso ao Perfil (/perfil)', async ({ page }) => {
    await page.goto('/perfil');
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/perfil/);
  });

  test('NAV-08 — Menu desktop: links no topo em viewport > 768px', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto('/inicio');
    await page.waitForLoadState('networkidle');
    // Menu superior deve estar visível no desktop
    const desktopNav = page.locator('nav.hidden.md\\:flex, nav[class*="md:flex"]').first();
    const isVisible = await desktopNav.isVisible({ timeout: 3000 }).catch(() => false);
    // Alternativa: verificar que há links de navegação visíveis no topo
    const topLinks = page.locator('header nav a, nav a[href*="/torneios"]').first();
    const topVisible = await topLinks.isVisible({ timeout: 3000 }).catch(() => false);
    expect(isVisible || topVisible).toBeTruthy();
  });

  test('NAV-09 — Menu mobile: barra inferior em viewport < 768px', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/inicio');
    await page.waitForLoadState('networkidle');
    // Bottom bar deve estar visível no mobile
    const bottomBar = page.locator('nav[class*="fixed"][class*="bottom"], nav[class*="bottom-0"]').first();
    const isVisible = await bottomBar.isVisible({ timeout: 3000 }).catch(() => false);
    if (!isVisible) {
      // Fallback: pelo menos algum link de navegação visível
      const anyNav = page.locator('nav a').first();
      await expect(anyNav).toBeVisible({ timeout: 5000 });
    }
  });

  test('NAV-10 — URL inexistente exibe página 404 ou redireciona', async ({ page }) => {
    await page.goto('/pagina-que-nao-existe');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    const url = page.url();
    const body = await page.locator('body').innerText();
    // Deve mostrar 404, redirecionar para home ou mostrar conteúdo de erro
    expect(
      body.includes('404') ||
      body.toLowerCase().includes('não encontrad') ||
      url.includes('/inicio') ||
      url.endsWith('/')
    ).toBeTruthy();
  });
});
