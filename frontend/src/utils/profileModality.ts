const KEY_PREFIX = 'th_modality_pref_';

export function getProfileModality(profileId: number): string {
  try {
    return localStorage.getItem(`${KEY_PREFIX}${profileId}`) || '';
  } catch {
    return '';
  }
}

export function setProfileModality(profileId: number, modality: string): void {
  try {
    if (modality) {
      localStorage.setItem(`${KEY_PREFIX}${profileId}`, modality);
    } else {
      localStorage.removeItem(`${KEY_PREFIX}${profileId}`);
    }
  } catch {}
}

// Sincroniza o valor do backend para o cache local.
// Chamado após carregar o perfil da API para garantir consistência entre dispositivos.
export function syncModalityFromProfile(profile: { id: number; preferred_modality?: string }): void {
  if (profile.preferred_modality) {
    setProfileModality(profile.id, profile.preferred_modality);
  }
}

export const MODALITY_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'Não definida' },
  { value: 'tennis', label: 'Tênis' },
  { value: 'beach_tennis', label: 'Beach Tennis' },
  { value: 'padel', label: 'Padel' },
  { value: 'wheelchair', label: 'Tênis em cadeira de rodas' },
];
