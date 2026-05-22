const ACTIVE_PROFILE_PREFIX = 'th_active_profile_';

export function getActiveProfileId(userId: number): number | null {
  try {
    const raw = localStorage.getItem(`${ACTIVE_PROFILE_PREFIX}${userId}`);
    if (!raw) return null;
    const id = Number(raw);
    return Number.isFinite(id) && id > 0 ? id : null;
  } catch {
    return null;
  }
}

export function setActiveProfileId(userId: number, profileId: number): void {
  try {
    localStorage.setItem(`${ACTIVE_PROFILE_PREFIX}${userId}`, String(profileId));
  } catch {}
}

export function clearActiveProfileId(userId: number): void {
  try {
    localStorage.removeItem(`${ACTIVE_PROFILE_PREFIX}${userId}`);
  } catch {}
}
