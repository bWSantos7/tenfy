import { test, expect } from '@playwright/test';
import * as dotenv from 'dotenv';
import * as path from 'path';
import { login, logout, screenshotStep, CREDS } from '../utils/helpers';

dotenv.config({ path: path.resolve(__dirname, '../.env.qa') });

// ─────────────────────────────────────────────────────────────────────────────
// AUTENTICAÇÃO — Cenários 1 e 2
// Valida que login funciona para responsável e dependente,
// que sessão é estabelecida e que logout limpa a sessão.
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Auth — Login e Logout', () => {

  // ── Cenário 1: Login como Responsável ─────────────────────────────────────
  test('C01 — Login como Responsável', async ({ page }) => {
    console.log('\n🧪 C01 — Login como Responsável');
    const steps: string[] = [];

    await page.goto('/login');
    await page.waitForLoadState('networkidle');
    steps.push('Acessou /login');

    // Verifica campos do formulário
    await expect(page.locator('[data-testid="login-email"]')).toBeVisible();
    await expect(page.locator('[data-testid="login-password"]')).toBeVisible();
    steps.push('Campos de e-mail e senha visíveis');

    await screenshotStep(page, 'auth', 'c01-login-page');

    // Preenche credenciais
    await page.locator('[data-testid="login-email"]').fill(CREDS.responsavel.email);
    await page.locator('[data-testid="login-password"]').fill(CREDS.responsavel.password);
    steps.push(`Preencheu e-mail: ${CREDS.responsavel.email}`);

    await screenshotStep(page, 'auth', 'c01-filled-form');

    // Submete
    await page.locator('[data-testid="login-submit"]').click();
    steps.push('Clicou em "Entrar na conta"');

    // Espera redirecionamento
    await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 20_000 });
    steps.push(`Redirecionado para: ${page.url()}`);

    // Verifica se chegou na home ou /inicio
    expect(page.url()).not.toContain('/login');
    const currentUrl = page.url();
    expect(currentUrl).toMatch(/\/(inicio|home|torneios)?/);
    steps.push('URL não contém /login (sessão ativa confirmada)');

    await screenshotStep(page, 'auth', 'c01-logged-in');

    // Verifica ausência de erro de login
    const errorEl = page.locator('[data-testid="login-error"]');
    await expect(errorEl).not.toBeVisible();
    steps.push('Nenhuma mensagem de erro exibida');

    console.log('  Passos executados:', steps);
    console.log('  ✅ APROVADO — Login do Responsável funcionou corretamente');
  });

  // ── Cenário 1b: Rejeita credenciais inválidas ─────────────────────────────
  test('C01b — Rejeita credenciais inválidas', async ({ page }) => {
    console.log('\n🧪 C01b — Credenciais inválidas devem mostrar erro');

    await page.goto('/login');
    await page.waitForLoadState('networkidle');

    await page.locator('[data-testid="login-email"]').fill('invalido@naoexiste.com');
    await page.locator('[data-testid="login-password"]').fill('senha_errada_123');
    await page.locator('[data-testid="login-submit"]').click();

    // Aguarda mensagem de erro aparecer
    await expect(page.locator('[data-testid="login-error"]')).toBeVisible({ timeout: 15_000 });
    const errorText = await page.locator('[data-testid="login-error"]').textContent();
    expect(errorText).toBeTruthy();

    // Deve permanecer na tela de login
    expect(page.url()).toContain('/login');

    await screenshotStep(page, 'auth', 'c01b-invalid-credentials');
    console.log('  ✅ APROVADO — Mensagem de erro exibida corretamente');
  });

  // ── Cenário 2: Login como Dependente ─────────────────────────────────────
  test('C02 — Login como Dependente', async ({ page }) => {
    console.log('\n🧪 C02 — Login como Dependente');
    const steps: string[] = [];

    await page.goto('/login');
    await page.waitForLoadState('networkidle');
    steps.push('Acessou /login');

    await page.locator('[data-testid="login-email"]').fill(CREDS.dependente.email);
    await page.locator('[data-testid="login-password"]').fill(CREDS.dependente.password);
    steps.push(`Preencheu e-mail: ${CREDS.dependente.email}`);

    await screenshotStep(page, 'auth', 'c02-filled-form');
    await page.locator('[data-testid="login-submit"]').click();
    steps.push('Clicou em "Entrar na conta"');

    await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 20_000 });
    steps.push(`Redirecionado para: ${page.url()}`);

    expect(page.url()).not.toContain('/login');
    steps.push('Sessão do Dependente estabelecida');

    await screenshotStep(page, 'auth', 'c02-logged-in');

    console.log('  Passos executados:', steps);
    console.log('  ✅ APROVADO — Login do Dependente funcionou corretamente');
  });

  // ── Cenário: Logout limpa a sessão ───────────────────────────────────────
  test('C02b — Logout limpa sessão e redireciona para login', async ({ page }) => {
    console.log('\n🧪 C02b — Logout limpa sessão');

    // Faz login
    await login(page, CREDS.responsavel.email, CREDS.responsavel.password, 'Responsável');

    // Limpa storage (simula logout)
    await logout(page);

    // Tenta acessar rota protegida
    await page.goto('/inicio');
    await page.waitForLoadState('networkidle');

    // Deve redirecionar para login
    await page.waitForURL((url) => url.pathname.includes('/login'), { timeout: 10_000 });
    expect(page.url()).toContain('/login');

    await screenshotStep(page, 'auth', 'c02b-after-logout');
    console.log('  ✅ APROVADO — Logout limpou sessão e redirecionou para /login');
  });
});
