import { Page, expect } from '@playwright/test';

export class WatchlistPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto('/watchlist');
    await this.page.waitForLoadState('networkidle');
    const modal = this.page.getByRole('button', { name: /entendi/i });
    if (await modal.isVisible({ timeout: 2000 }).catch(() => false)) {
      await modal.click();
      await this.page.waitForTimeout(300);
    }
    await this.page.waitForTimeout(1500);
  }

  async countItems(): Promise<number> {
    return this.page.locator('.card').count();
  }

  async expectMonthGroupVisible() {
    // Grupos de mês existem como cabeçalhos (Janeiro 2026, etc.)
    const months = /janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro/i;
    const headers = this.page.getByText(months);
    const count = await headers.count();
    return count > 0;
  }

  async expectTournamentInList(partialTitle: string) {
    await expect(
      this.page.getByText(partialTitle, { exact: false })
    ).toBeVisible({ timeout: 8000 });
  }

  async expectEmptyState() {
    await expect(
      this.page.getByText(/nenhuma|sem torneio|agenda vazia/i)
    ).toBeVisible({ timeout: 8000 });
  }
}
