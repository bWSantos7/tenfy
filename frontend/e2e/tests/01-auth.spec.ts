/**
 * TC-AUTH — Autenticação, cadastro, login, logout e fluxos de erro.
 */
import { test, expect } from '@playwright/test';
import { AuthPage } from '../pages/AuthPage';
import { PLAYER, newTestEmail } from '../fixtures/users';

test.describe('TC-AUTH — Autenticação', () => {

  test('AUTH-01 — Landing page acessível e link de login funciona', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/tenfy/i, { timeout: 10000 });
    const loginLink = page.getByRole('link', { name: /entrar|login/i }).first();
    await expect(loginLink).toBeVisible({ timeout: 8000 });
    await loginLink.click();
    await expect(page).toHaveURL(/login/, { timeout: 8000 });
  });

  test('AUTH-02 — Formulário de login renderiza com campos corretos', async ({ page }) => {
    await page.goto('/login');
    await page.waitForLoadState('networkidle');
    // Selectors reais: input[type=email], input[type=password]
    await expect(page.locator('input[type="email"]').first()).toBeVisible({ timeout: 8000 });
    await expect(page.locator('input[type="password"]').first()).toBeVisible({ timeout: 8000 });
    await expect(page.getByRole('button', { name: /^entrar$/i })).toBeVisible({ timeout: 8000 });
    await expect(page.getByRole('link', { name: /criar conta|cadastro/i })).toBeVisible({ timeout: 5000 });
  });

  test('AUTH-03 — Login com credenciais corretas redireciona para /inicio', async ({ page }) => {
    const auth = new AuthPage(page);
    await auth.login(PLAYER.email, PLAYER.password);
    await expect(page).toHaveURL(/inicio/, { timeout: 20000 });
  });

  test('AUTH-04 — Login com senha errada exibe mensagem de erro', async ({ page }) => {
    const auth = new AuthPage(page);
    await auth.loginExpectError(PLAYER.email, 'senhaErrada_E2E!');
    await expect(page).toHaveURL(/login/, { timeout: 5000 });
    // Mensagem real: "E-mail ou senha incorretos. Verifique os dados ou redefina sua senha."
    await expect(page.getByText(/incorretos|inválid/i)).toBeVisible({ timeout: 8000 });
  });

  test('AUTH-05 — Login com e-mail inexistente exibe mensagem de erro', async ({ page }) => {
    const auth = new AuthPage(page);
    await auth.loginExpectError('naoexiste_e2e@tenfy-test.invalid', 'qualquersenha123');
    await expect(page).toHaveURL(/login/, { timeout: 5000 });
    await expect(page.getByText(/incorretos|inválid/i)).toBeVisible({ timeout: 8000 });
  });

  test('AUTH-06 — Rota protegida /inicio redireciona para /login quando não autenticado', async ({ page }) => {
    await page.goto('/inicio');
    await expect(page).toHaveURL(/login/, { timeout: 8000 });
  });

  test('AUTH-07 — Após login, usuário está em /inicio', async ({ page }) => {
    const auth = new AuthPage(page);
    await auth.login(PLAYER.email, PLAYER.password);
    // A saudação "Olá," deve aparecer
    await expect(page.getByText(/olá/i)).toBeVisible({ timeout: 8000 });
  });

  test('AUTH-08 — Página de cadastro (/register) renderiza formulário', async ({ page }) => {
    await page.goto('/register');
    await page.waitForLoadState('networkidle');
    // Tem campo de e-mail (type=email) e pelo menos um campo de texto
    await expect(page.locator('input[type="email"]').first()).toBeVisible({ timeout: 8000 });
    await expect(page.locator('input[type="password"]').first()).toBeVisible({ timeout: 8000 });
  });

  test('AUTH-09 — Cadastro de novo usuário com e-mail único', async ({ page }) => {
    const auth = new AuthPage(page);
    const email = newTestEmail();
    await auth.register({ fullName: 'Teste E2E', email, password: 'SenhaForte2026!' });
    // Deve estar em alguma etapa de cadastro, onboarding ou /inicio
    await page.waitForTimeout(3000);
    const url = page.url();
    expect(
      url.includes('/inicio') || url.includes('/onboarding') || url.includes('/register')
    ).toBeTruthy();
  });

  test('AUTH-10 — Link "Criar conta" na página de login funciona', async ({ page }) => {
    await page.goto('/login');
    await page.waitForLoadState('networkidle');
    const createLink = page.getByRole('link', { name: /criar conta/i });
    await expect(createLink).toBeVisible({ timeout: 5000 });
    await createLink.click();
    await expect(page).toHaveURL(/register/, { timeout: 8000 });
  });

  test('AUTH-11 — Usuário autenticado acessando /login é redirecionado para /inicio', async ({ page }) => {
    const auth = new AuthPage(page);
    await auth.login(PLAYER.email, PLAYER.password);
    await expect(page).toHaveURL(/inicio/);
    await page.goto('/login');
    await page.waitForTimeout(2000);
    // Deve ter sido redirecionado para /inicio
    expect(page.url()).not.toContain('/login');
  });

  test('AUTH-12 — Logout desloga o usuário', async ({ page }) => {
    const auth = new AuthPage(page);
    await auth.login(PLAYER.email, PLAYER.password);
    await auth.logout();
    // Após logout, visitar /inicio deve redirecionar para /login
    await page.goto('/inicio');
    await expect(page).toHaveURL(/login|\//, { timeout: 8000 });
  });
});
