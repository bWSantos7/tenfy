import { Page, expect } from '@playwright/test';

export class TournamentsPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto('/torneios');
    await this.page.waitForLoadState('networkidle');
    // Descarta modal "Versão Beta" se aparecer
    const modal = this.page.getByRole('button', { name: /entendi/i });
    if (await modal.isVisible({ timeout: 2000 }).catch(() => false)) {
      await modal.click();
      await this.page.waitForTimeout(300);
    }
    await this.page.waitForTimeout(1500);
  }

  async applyModalityFilter(modality: string) {
    const select = this.page.locator('select').filter({ hasText: /modalidade|tênis|beach/i }).first();
    if (await select.isVisible({ timeout: 3000 }).catch(() => false)) {
      await select.selectOption(modality);
      await this.page.waitForTimeout(1500);
    }
  }

  async applyStateFilter(uf: string) {
    const select = this.page.locator('select').filter({ hasText: /estado|uf|all/i }).first();
    if (!await select.isVisible({ timeout: 2000 }).catch(() => false)) {
      // Tenta por placeholder
      const input = this.page.getByPlaceholder(/estado/i);
      if (await input.isVisible({ timeout: 2000 }).catch(() => false)) {
        await input.fill(uf);
        await this.page.waitForTimeout(800);
      }
      return;
    }
    await select.selectOption(uf);
    await this.page.waitForTimeout(1500);
  }

  async applyTextSearch(text: string) {
    const searchInput = this.page.getByPlaceholder(/buscar|pesquisar|torneio/i).first();
    await searchInput.fill(text);
    await this.page.waitForTimeout(1500);
  }

  async clearFilters() {
    const clearBtn = this.page.getByRole('button', { name: /limpar/i });
    if (await clearBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await clearBtn.click();
      await this.page.waitForTimeout(1000);
    }
  }

  async countCards(): Promise<number> {
    const cards = this.page.locator('.card, [data-testid="tournament-card"]');
    return await cards.count();
  }

  async openFirstTournament() {
    const firstCard = this.page.locator('a[href*="/torneios/"]').first();
    await firstCard.click();
    await this.page.waitForLoadState('networkidle');
    await this.page.waitForTimeout(1000);
  }

  async goBack() {
    await this.page.goBack();
    await this.page.waitForLoadState('networkidle');
    await this.page.waitForTimeout(1000);
  }

  async expectTournamentsVisible() {
    await expect(this.page.locator('a[href*="/torneios/"]').first()).toBeVisible({ timeout: 10000 });
  }

  async expectNoResults() {
    await expect(
      this.page.getByText(/nenhum torneio|sem resultados|não encontrado/i)
    ).toBeVisible({ timeout: 8000 });
  }
}
