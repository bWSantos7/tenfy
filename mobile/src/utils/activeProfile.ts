import { storage } from '../services/api';

const ACTIVE_PROFILE_PREFIX = 'th_active_profile';

export function activeProfileKey(userId: number): string {
  return `${ACTIVE_PROFILE_PREFIX}_${userId}`;
}

export async function getActiveProfileId(userId: number): Promise<number | null> {
  const raw = await storage.get(activeProfileKey(userId));
  const id = raw ? Number(raw) : NaN;
  return Number.isFinite(id) && id > 0 ? id : null;
}

export async function setActiveProfileId(userId: number, profileId: number): Promise<void> {
  await storage.set(activeProfileKey(userId), String(profileId));
}
