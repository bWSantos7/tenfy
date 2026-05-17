import api from './api';
import { TournamentRegistration } from '../types';

export async function myRegistrations(): Promise<TournamentRegistration[]> {
  const { data } = await api.get('/api/registrations/my/');
  return Array.isArray(data) ? data : (data.results ?? []);
}

export async function withdrawRegistration(id: number): Promise<void> {
  await api.delete(`/api/registrations/${id}/withdraw/`);
}
