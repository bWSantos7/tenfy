/**
 * Global setup: garante que os usuários e perfis de teste existam antes de qualquer teste.
 * Estratégia: tenta login → se falhar, registra → então verifica/cria perfil esportivo.
 */
import { FullConfig } from '@playwright/test';

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? 'https://www.tennis.app.br';
const API_URL  = BASE_URL.includes('localhost') ? 'http://localhost:8000' : 'https://api.tennis.app.br';

const TEST_USERS = [
  {
    email: 'player@tenfy-test.invalid', password: 'TestPlayer2026!',
    full_name: 'Carlos Jogador', role: 'player',
    profile: {
      display_name: 'Carlos Jogador', birth_year: 2008, gender: 'M',
      home_state: 'SP', home_city: 'São Paulo', travel_states: ['SP', 'RJ', 'MG'],
      competitive_level: 'federated', tennis_class: '4',
      preferred_modality: 'tennis', is_primary: true,
    },
  },
  {
    email: 'parent@tenfy-test.invalid', password: 'TestParent2026!',
    full_name: 'Maria Responsavel', role: 'parent',
    profile: null, // responsável não tem perfil esportivo próprio
  },
  {
    email: 'child1@tenfy-test.invalid', password: 'TestChild12026!',
    full_name: 'Ana Silva', role: 'player',
    profile: {
      display_name: 'Ana Silva', birth_year: 2012, gender: 'F',
      home_state: 'SP', home_city: 'Campinas', travel_states: ['SP'],
      competitive_level: 'federated', tennis_class: '3',
      preferred_modality: 'tennis', is_primary: true,
    },
  },
  {
    email: 'child2@tenfy-test.invalid', password: 'TestChild22026!',
    full_name: 'Bruno Lima', role: 'player',
    profile: {
      display_name: 'Bruno Lima', birth_year: 2010, gender: 'M',
      home_state: 'RJ', home_city: 'Rio de Janeiro', travel_states: ['RJ', 'SP'],
      competitive_level: 'amateur', tennis_class: '',
      preferred_modality: 'beach_tennis', is_primary: true,
    },
  },
];

async function apiPost(url: string, body: object, token?: string): Promise<{ ok: boolean; status: number; data: any }> {
  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch(url, { method: 'POST', headers, body: JSON.stringify(body) });
    let data: any = {};
    try { data = await res.json(); } catch {}
    return { ok: res.ok, status: res.status, data };
  } catch (err) {
    return { ok: false, status: 0, data: { error: String(err) } };
  }
}

async function apiGet(url: string, token: string): Promise<{ ok: boolean; data: any }> {
  try {
    const res = await fetch(url, { headers: { 'Authorization': `Bearer ${token}` } });
    let data: any = {};
    try { data = await res.json(); } catch {}
    return { ok: res.ok, data };
  } catch (err) {
    return { ok: false, data: { error: String(err) } };
  }
}

export default async function globalSetup(_config: FullConfig) {
  console.log('\n🔧  Global setup: verificando usuários e perfis de teste...');
  console.log(`    API: ${API_URL}`);

  for (const u of TEST_USERS) {
    // 1. Tenta login para obter token
    const loginRes = await apiPost(`${API_URL}/api/auth/login/`, {
      email: u.email, password: u.password,
    });

    let token: string | null = loginRes.ok ? loginRes.data?.access : null;

    if (!token) {
      // 2. Login falhou → tenta registrar
      const regRes = await apiPost(`${API_URL}/api/auth/register/`, {
        email: u.email, password: u.password, password_confirm: u.password,
        full_name: u.full_name, role: u.role,
        accept_terms: true, marketing_consent: false,
      });

      if (regRes.ok) {
        token = regRes.data?.access ?? null;
        console.log(`  ✅  ${u.email} — cadastrado`);
      } else {
        const errStr = JSON.stringify(regRes.data).toLowerCase();
        if (errStr.includes('cadastro') || errStr.includes('email') || errStr.includes('unique')) {
          console.warn(`  ⚠️   ${u.email} — existe mas com senha diferente; execute seed_test_data --reset`);
        } else {
          console.warn(`  ❌  ${u.email} — erro ${regRes.status}: ${JSON.stringify(regRes.data).slice(0, 80)}`);
        }
        continue;
      }
    } else {
      console.log(`  ✅  ${u.email} — login OK`);
    }

    if (!token || !u.profile) continue;

    // 3. Verifica se já tem perfil
    const profilesRes = await apiGet(`${API_URL}/api/players/profiles/`, token);
    const existingProfiles = profilesRes.ok
      ? (profilesRes.data?.results ?? profilesRes.data ?? [])
      : [];

    if (Array.isArray(existingProfiles) && existingProfiles.length > 0) {
      console.log(`  ✅  ${u.email} — perfil existente`);
      continue;
    }

    // 4. Cria perfil esportivo
    const profRes = await apiPost(`${API_URL}/api/players/profiles/`, u.profile, token);
    if (profRes.ok) {
      console.log(`  ✅  ${u.email} — perfil criado (${u.profile.preferred_modality})`);
    } else {
      console.warn(`  ⚠️   ${u.email} — erro ao criar perfil: ${JSON.stringify(profRes.data).slice(0, 80)}`);
    }
  }

  console.log('🔧  Global setup concluído.\n');
}
