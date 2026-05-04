import { PlayerProfile } from '../types';

export function pickBestProfile(profiles: PlayerProfile[]): PlayerProfile | null {
  if (!profiles.length) return null;

  const scored = [...profiles].sort((a, b) => scoreProfile(b) - scoreProfile(a));
  return scored[0] || null;
}

function scoreProfile(profile: PlayerProfile): number {
  let score = 0;
  if (profile.birth_year) score += 10;
  if (profile.gender) score += 10;
  if (profile.tennis_class) score += 10;
  if (profile.categories.length > 0) score += 8;
  if (profile.home_state) score += 2;
  if (profile.home_city) score += 1;
  if (profile.is_primary) score += 5;
  return score;
}
