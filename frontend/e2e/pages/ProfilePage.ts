import { Page, expect } from '@playwright/test';

export class ProfilePage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto('/perfil');
    await this.page.waitForLoadState('networkidle');
    const modal = this.page.getByRole('button', { name: /entendi/i });
    if (await modal.isVisible({ timeout: 2000 }).catch(() => false)) {
      await modal.click();
      await this.page.waitForTimeout(300);
    }
    await this.page.waitForTimeout(1500);
  }

  async editProfile() {
    const editBtn = this.page.getByRole('button', { name: /editar|alterar perfil/i }).first();
    await editBtn.click();
    await this.page.waitForTimeout(500);
  }

  async saveProfile() {
    const saveBtn = this.page.getByRole('button', { name: /salvar/i }).first();
    await saveBtn.click();
    await this.page.waitForTimeout(2000);
  }

  async selectModality(value: string) {
    const sel = this.page.locator('select').filter({ hasText: /modalidade/i }).first();
    if (await sel.isVisible({ timeout: 3000 }).catch(() => false)) {
      await sel.selectOption(value);
    }
  }

  async selectState(uf: string) {
    const sel = this.page.locator('select').filter({ hasText: /estado|uf/i }).first();
    if (await sel.isVisible({ timeout: 3000 }).catch(() => false)) {
      await sel.selectOption(uf);
    }
  }

  async expectProfileName(name: string) {
    await expect(this.page.getByText(name)).toBeVisible({ timeout: 8000 });
  }

  async expectSuccessToast() {
    await expect(
      this.page.getByText(/atualizado|salvo|sucesso/i)
    ).toBeVisible({ timeout: 8000 });
  }

  // ─── Dependentes ──────────────────────────────────────────────────────────
  async addDependent(data: { fullName: string; email: string; password: string }) {
    const addBtn = this.page.getByRole('button', { name: /adicionar dependente|novo dependente|cadastrar dependente/i });
    await addBtn.click();
    await this.page.waitForTimeout(500);

    await this.page.getByPlaceholder(/nome/i).fill(data.fullName);
    await this.page.getByPlaceholder(/e-mail/i).fill(data.email);
    const passwordFields = await this.page.getByPlaceholder(/senha/i).all();
    await passwordFields[0]?.fill(data.password);
    await passwordFields[1]?.fill(data.password);

    await this.page.getByRole('button', { name: /salvar|cadastrar|confirmar/i }).last().click();
    await this.page.waitForTimeout(3000);
  }

  async expectDependentListed(name: string) {
    await expect(this.page.getByText(name, { exact: false })).toBeVisible({ timeout: 8000 });
  }
}
