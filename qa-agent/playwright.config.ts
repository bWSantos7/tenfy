import { defineConfig, devices } from '@playwright/test';
import * as dotenv from 'dotenv';
import * as path from 'path';

// Carrega variáveis do .env.qa (na raiz do qa-agent)
dotenv.config({ path: path.resolve(__dirname, '.env.qa') });

export default defineConfig({
  testDir: './tests',
  fullyParallel: false, // Testes sequenciais para evitar conflitos de sessão
  forbidOnly: !!process.env.CI,
  retries: 1,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 15_000 },

  reporter: [
    ['list'],
    ['html', { outputFolder: 'reports/html', open: 'never' }],
    ['json', { outputFile: 'reports/results.json' }],
  ],

  use: {
    baseURL: process.env.WEB_URL || 'https://www.tennis.app.br',
    trace: 'on',                          // Sempre salvar trace
    screenshot: 'on',                     // Screenshot em cada passo
    video: 'retain-on-failure',           // Vídeo só em falha
    headless: true,
    locale: 'pt-BR',
    timezoneId: 'America/Sao_Paulo',
    viewport: { width: 390, height: 844 }, // Viewport mobile (iPhone 14)
    ignoreHTTPSErrors: true,
    actionTimeout: 20_000,
    navigationTimeout: 30_000,
  },

  outputDir: 'reports/test-results',

  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['iPhone 14'],
        // Usar desktop para testes de filtros (melhor visibilidade)
        viewport: { width: 1280, height: 800 },
        isMobile: false,
      },
    },
  ],
});
