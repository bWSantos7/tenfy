/** Credenciais espelhando o seed_test_data.py */
export const PLAYER = {
  email: 'player@tenfy-test.invalid',
  password: 'TestPlayer2026!',
  fullName: 'Carlos Jogador',
};

export const PARENT = {
  email: 'parent@tenfy-test.invalid',
  password: 'TestParent2026!',
  fullName: 'Maria Responsável',
};

export const CHILD1 = {
  email: 'child1@tenfy-test.invalid',
  password: 'TestChild12026!',
  fullName: 'Ana Silva',
};

export const CHILD2 = {
  email: 'child2@tenfy-test.invalid',
  password: 'TestChild22026!',
  fullName: 'Bruno Lima',
};

/** Usuário para testes de cadastro (gerado dinamicamente) */
export function newTestEmail(): string {
  return `e2e-${Date.now()}@tenfy-test.invalid`;
}
