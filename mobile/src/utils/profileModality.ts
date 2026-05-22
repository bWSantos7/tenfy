import { storage } from '../services/api';

const KEY_PREFIX = 'th_modality_pref_';

export async function getProfileModality(profileId: number): Promise<string> {
  try {
    return (await storage.get(`${KEY_PREFIX}${profileId}`)) || '';
  } catch {
    return '';
  }
}

export async function setProfileModality(profileId: number, modality: string): Promise<void> {
  try {
    if (modality) {
      await storage.set(`${KEY_PREFIX}${profileId}`, modality);
    } else {
      await storage.delete(`${KEY_PREFIX}${profileId}`);
    }
  } catch {}
}

// Sincroniza o valor do backend para o cache local.
// Chamado após carregar o perfil da API para garantir consistência entre dispositivos.
export async function syncModalityFromProfile(profile: { id: number; preferred_modality?: string }): Promise<void> {
  if (profile.preferred_modality) {
    await setProfileModality(profile.id, profile.preferred_modality);
  }
}

export const MODALITY_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'Não definida' },
  { value: 'tennis', label: 'Tênis' },
  { value: 'beach_tennis', label: 'Beach Tennis' },
  { value: 'padel', label: 'Padel' },
  { value: 'wheelchair', label: 'Tênis em cadeira de rodas' },
];
