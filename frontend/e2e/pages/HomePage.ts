import { Page, expect } from '@playwright/test';

export class HomePage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto('/inicio');
    await this.page.waitForLoadState('networkidle');
    await this.page.waitForTimeout(2000);
  }

  async expectGreeting(name: string) {
    await expect(this.page.getByText(name, { exact: false })).toBeVisible({ timeout: 8000 });
  }

  async expectCompatibleSection() {
    await expect(
      this.page.getByText(/compatíveis/i)
    ).toBeVisible({ timeout: 8000 });
  }

  async expectAlertBadge() {
    const badge = this.page.locator('[class*="rounded-full"]').filter({ hasText: /\d/ });
    return badge.isVisible({ timeout: 3000 }).catch(() => false);
  }

  async getCompatibleTournamentCount(): Promise<number> {
    const section = this.page.locator('section').filter({ hasText: /compatíveis/i }).first();
    return section.locator('a[href*="/torneios/"]').count();
  }
}
