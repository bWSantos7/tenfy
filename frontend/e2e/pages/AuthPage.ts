import { Page, expect } from '@playwright/test';

export class AuthPage {
  constructor(private page: Page) {}

  /** Selectors baseados no HTML real do LoginPage.tsx */
  private email()     { return this.page.locator('input[type="email"]').first(); }
  private password()  { return this.page.locator('input[type="password"]').first(); }
  private submitBtn() { return this.page.getByRole('button', { name: /^entrar$/i }); }

  /** Dismiss o modal "Versão Beta" se estiver visível. */
  async dismissBetaModal() {
    const btn = this.page.getByRole('button', { name: /entendi/i });
    if (await btn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await btn.click();
      await this.page.waitForTimeout(500);
    }
  }

  /**
   * Faz login navegando primeiro para /inicio (rota protegida),
   * o que faz o PrivateRoute redirecionar para /login com state.from=/inicio.
   * Assim, após login bem-sucedido, nav(from) leva de volta a /inicio.
   * Também descarta o modal "Versão Beta" se presente.
   */
  async login(email: string, password: string) {
    // Patch localStorage before first navigation — suppresses BetaModal for the entire
    // browser context. The modal checks localStorage.getItem('th_beta_ack_{userId}');
    // returning '1' for any th_beta_ack* key prevents it from ever rendering.
    await this.page.context().addInitScript(() => {
      const orig = Storage.prototype.getItem;
      Storage.prototype.getItem = function (key: string) {
        if (key && key.startsWith('th_beta_ack')) return '1';
        return orig.call(this, key);
      };
    });
    await this.page.goto('/inicio');
    await this.page.waitForURL(/\/login/, { timeout: 10_000 });
    await this.email().waitFor({ state: 'visible', timeout: 10_000 });
    await this.email().fill(email);
    await this.password().fill(password);
    await this.submitBtn().click();
    await this.page.waitForURL(/\/inicio/, { timeout: 20_000 });
    // Descarta o modal "Versão Beta" que aparece na primeira visita de cada contexto
    await this.dismissBetaModal();
  }

  async loginExpectError(email: string, password: string) {
    await this.page.goto('/login');
    await this.page.waitForLoadState('networkidle');
    await this.email().waitFor({ state: 'visible', timeout: 8_000 });
    await this.email().fill(email);
    await this.password().fill(password);
    await this.submitBtn().click();
    await this.page.waitForTimeout(3000);
  }

  async logout() {
    await this.page.goto('/perfil');
    await this.page.waitForLoadState('networkidle');
    const logoutBtn = this.page.getByRole('button', { name: /sair|logout/i });
    if (await logoutBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await logoutBtn.click();
      await this.page.waitForTimeout(2000);
    }
  }

  async register(data: { fullName: string; email: string; password: string }) {
    await this.page.goto('/register');
    await this.page.waitForLoadState('networkidle');
    await this.page.getByPlaceholder(/ex: maria|nome/i).first().fill(data.fullName);
    await this.page.locator('input[type="email"]').fill(data.email);
    await this.page.getByPlaceholder(/mínimo 8/i).fill(data.password);
    await this.page.getByPlaceholder(/repita a senha/i).fill(data.password);
    const check = this.page.getByRole('checkbox').first();
    if (await check.isVisible({ timeout: 2000 }).catch(() => false)) await check.check();
    await this.page.getByRole('button', { name: /próximo|criar conta|continuar/i }).first().click();
    await this.page.waitForTimeout(2000);
  }

  async isLoggedIn(): Promise<boolean> {
    return /\/(inicio|perfil|torneios|watchlist)/i.test(this.page.url());
  }

  async expectErrorMessage(text: RegExp | string) {
    await expect(this.page.getByText(text)).toBeVisible({ timeout: 8000 });
  }

  async expectLoginForm() {
    await expect(this.email()).toBeVisible({ timeout: 8000 });
    await expect(this.password()).toBeVisible({ timeout: 8000 });
    await expect(this.submitBtn()).toBeVisible({ timeout: 8000 });
  }
}
