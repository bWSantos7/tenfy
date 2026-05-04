import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Star, Loader2, Trash2, ExternalLink } from 'lucide-react';
import toast from 'react-hot-toast';
import { WatchlistItem } from '../types';
import { listWatchlist, deleteWatch } from '../services/data';
import { TournamentCard } from '../components/TournamentCard';
import { extractApiError } from '../services/api';

export const WatchlistPage: React.FC = () => {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const data = await listWatchlist();
      setItems(data);
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function remove(id: number) {
    try {
      await deleteWatch(id);
      setItems((prev) => prev.filter((x) => x.id !== id));
      toast.success('Removido da agenda');
    } catch (err) {
      toast.error(extractApiError(err));
    }
  }

  if (loading) {
    return (
      <div className="py-16 flex justify-center">
        <Loader2 className="w-8 h-8 text-accent-neon animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Sua agenda</h1>
      {items.length === 0 ? (
        <div className="card text-center py-10">
          <Star className="w-10 h-10 text-text-muted mx-auto mb-3" />
          <p className="text-sm text-text-secondary mb-4">
            Você ainda não está acompanhando nenhum torneio.
          </p>
          <Link to="/torneios" className="btn-primary inline-flex items-center gap-1">
            Explorar torneios <ExternalLink className="w-4 h-4" />
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <div key={item.id} className="relative">
              <TournamentCard edition={item.edition_detail} />
              <button
                className="absolute top-2 right-2 p-2 rounded-lg bg-bg-elevated/80 hover:bg-bg-base text-status-canceled"
                onClick={(e) => { e.preventDefault(); remove(item.id); }}
                title="Remover da agenda"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
