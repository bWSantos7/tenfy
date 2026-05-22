import { defineConfig, devices } from '@playwright/test';

/**
 * Tenfy E2E Test Configuration
 * Base URL: produção (www.tennis.app.br) ou local (localhost:5173).
 * Defina PLAYWRIGHT_BASE_URL=http://localhost:5173 para rodar localmente.
 */
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? 'https://www.tennis.app.br';

export default defineConfig({
  testDir: './e2e/tests',
  globalSetup: './e2e/fixtures/global-setup.ts',
  fullyParallel: false,        // sequencial — evita conflito de dados entre testes
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  timeout: 30_000,
  expect: { timeout: 8_000 },

  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
    ['json', { outputFile: 'playwright-report/results.json' }],
  ],

  use: {
    baseURL: BASE_URL,
    headless: true,
    viewport: { width: 1280, height: 720 },
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'retain-on-failure',
    locale: 'pt-BR',
    timezoneId: 'America/Sao_Paulo',
  },

  projects: [
    {
      name: 'Desktop Chrome',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'Mobile Safari',
      use: { ...devices['iPhone 14'], viewport: { width: 390, height: 844 } },
    },
  ],
});
