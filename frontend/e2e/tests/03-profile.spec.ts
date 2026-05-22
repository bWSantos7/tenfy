/**
 * TC-PROFILE — Perfil esportivo: criação, edição, modalidade, persistência.
 */
import { test, expect } from '@playwright/test';
import { AuthPage } from '../pages/AuthPage';
import { ProfilePage } from '../pages/ProfilePage';
import { PLAYER } from '../fixtures/users';

test.describe('TC-PROFILE — Perfil esportivo', () => {

  test.beforeEach(async ({ page }) => {
    const auth = new AuthPage(page);
    await auth.login(PLAYER.email, PLAYER.password);
  });

  test('PROFILE-01 — Página de perfil carrega sem erros', async ({ page }) => {
    const profile = new ProfilePage(page);
    await profile.goto();
    await expect(page.locator('body')).not.toContainText(/erro|error|500|undefined/i);
  });

  test('PROFILE-02 — Nome do usuário aparece no perfil', async ({ page }) => {
    const profile = new ProfilePage(page);
    await profile.goto();
    // Nome "Carlos Jogador" ou e-mail do usuário deve aparecer
    const hasName = await page.getByText(/Carlos|Jogador|player@tenfy/i).first().isVisible({ timeout: 8000 }).catch(() => false);
    expect(hasName).toBeTruthy();
  });

  test('PROFILE-03 — Botão de editar perfil está disponível', async ({ page }) => {
    const profile = new ProfilePage(page);
    await profile.goto();
    const editBtn = page.getByRole('button', { name: /editar/i }).first();
    await expect(editBtn).toBeVisible({ timeout: 8000 });
  });

  test('PROFILE-04 — Campo modalidade aparece ao editar', async ({ page }) => {
    const profile = new ProfilePage(page);
    await profile.goto();
    await profile.editProfile();
    await page.waitForTimeout(500);
    // Campo de modalidade deve aparecer no formulário
    const modalityField = page.getByText(/modalidade/i).first();
    await expect(modalityField).toBeVisible({ timeout: 8000 });
  });

  test('PROFILE-05 — Editar e salvar modalidade persiste', async ({ page }) => {
    const profile = new ProfilePage(page);
    await profile.goto();
    await profile.editProfile();
    await profile.selectModality('tennis');
    await profile.saveProfile();
    await profile.expectSuccessToast();
    // Recarregar e verificar que persistiu
    await profile.goto();
    const hasTennis = await page.getByText(/tênis/i).first().isVisible({ timeout: 5000 }).catch(() => false);
    expect(hasTennis).toBeTruthy();
  });

  test('PROFILE-06 — Classe/nível aparece no perfil', async ({ page }) => {
    const profile = new ProfilePage(page);
    await profile.goto();
    const hasClass = await page.getByText(/classe|nível|federad/i).first().isVisible({ timeout: 5000 }).catch(() => false);
    expect(hasClass).toBeTruthy();
  });

  test('PROFILE-07 — Estado (UF) aparece no perfil', async ({ page }) => {
    const profile = new ProfilePage(page);
    await profile.goto();
    // SP deve aparecer no perfil do player de teste
    await expect(page.getByText(/SP/)).toBeVisible({ timeout: 8000 });
  });

  test('PROFILE-08 — Alterações persistem após sair e voltar', async ({ page }) => {
    const profile = new ProfilePage(page);
    await profile.goto();
    await profile.editProfile();
    await profile.selectModality('tennis');
    await profile.saveProfile();

    // Navegar para outra página e voltar
    await page.goto('/inicio');
    await page.waitForTimeout(1000);
    await profile.goto();

    // Perfil deve continuar com modalidade Tênis
    const body = await page.locator('body').innerText();
    expect(body.toLowerCase()).toMatch(/tênis|tennis/);
  });

  test('PROFILE-09 — Página de política de privacidade acessível', async ({ page }) => {
    await page.goto('/politica-privacidade');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('body')).not.toContainText(/404|not found/i);
    await expect(page.getByText(/privacidade|LGPD|dados/i).first()).toBeVisible({ timeout: 8000 });
  });
});
