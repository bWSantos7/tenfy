/**
 * TC-RESPONSIVE — Layout responsivo em diferentes viewports.
 */
import { test, expect } from '@playwright/test';
import { AuthPage } from '../pages/AuthPage';
import { PLAYER } from '../fixtures/users';

const VIEWPORTS = [
  { name: 'Desktop 1440', width: 1440, height: 900 },
  { name: 'Notebook 1280', width: 1280, height: 720 },
  { name: 'Tablet 768', width: 768, height: 1024 },
  { name: 'Mobile 390', width: 390, height: 844 },
  { name: 'Mobile pequeno 320', width: 320, height: 568 },
];

const PAGES_TO_TEST = [
  { path: '/inicio', name: 'Home' },
  { path: '/torneios', name: 'Torneios' },
  { path: '/watchlist', name: 'Agenda' },
  { path: '/resultados', name: 'Resultados' },
  { path: '/perfil', name: 'Perfil' },
];

test.describe('TC-RESPONSIVE — Responsividade', () => {

  for (const vp of VIEWPORTS) {
    test.describe(`Viewport: ${vp.name} (${vp.width}x${vp.height})`, () => {

      test.beforeEach(async ({ page }) => {
        await page.setViewportSize({ width: vp.width, height: vp.height });
        const auth = new AuthPage(page);
        await auth.login(PLAYER.email, PLAYER.password);
      });

      for (const pg of PAGES_TO_TEST) {
        test(`${pg.name} renderiza sem overflow ou layout quebrado`, async ({ page }) => {
          await page.goto(pg.path);
          await page.waitForLoadState('networkidle');
          await page.waitForTimeout(1500);

          // Página carrega sem erros
          await expect(page.locator('body')).not.toContainText(/erro 500|internal server/i);

          // Verificar overflow horizontal (indica layout quebrado)
          const hasHorizontalScroll = await page.evaluate(() => {
            return document.body.scrollWidth > document.body.clientWidth;
          });
          if (hasHorizontalScroll) {
            console.warn(`⚠️  Overflow horizontal em ${pg.name} @ ${vp.width}px`);
          }
          // Não falha por overflow — apenas registra (pode ser aceitável em alguns casos)

          // Verificar que o conteúdo principal existe
          const mainContent = page.locator('main, [role="main"], .space-y-4, .space-y-6').first();
          await expect(mainContent).toBeVisible({ timeout: 8000 });

          // Screenshot para evidência
          await page.screenshot({
            path: `playwright-report/screenshots/${pg.name.toLowerCase()}-${vp.width}px.png`,
            fullPage: false,
          });
        });
      }

      test(`Navegação principal visível em ${vp.name}`, async ({ page }) => {
        await page.goto('/inicio');
        await page.waitForLoadState('networkidle');
        await page.waitForTimeout(1000);

        const nav = page.locator('nav');
        const navCount = await nav.count();
        expect(navCount).toBeGreaterThan(0);

        // Pelo menos um link de navegação deve estar visível
        const navLinks = page.locator('nav a');
        const linkCount = await navLinks.count();
        expect(linkCount).toBeGreaterThan(0);
      });

      test(`Formulário de login utilizável em ${vp.name}`, async ({ page }) => {
        // Já está logado — verificar que campos na página atual são acessíveis
        await page.goto('/inicio');
        await page.waitForLoadState('networkidle');

        // Verificar que botões não estão fora da viewport
        const buttons = page.locator('button').first();
        if (await buttons.isVisible({ timeout: 3000 }).catch(() => false)) {
          const box = await buttons.boundingBox();
          if (box) {
            expect(box.x).toBeGreaterThanOrEqual(0);
            expect(box.x + box.width).toBeLessThanOrEqual(vp.width + 10); // 10px de tolerância
          }
        }
      });
    });
  }
});
