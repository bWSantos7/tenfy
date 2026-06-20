import React, { useMemo, useState } from 'react';
import { Search, ChevronDown, HelpCircle, PlayCircle } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { getHelpTopics, HelpTopic } from '../data/helpContent';
import { OPEN_TUTORIAL_EVENT } from '../components/InteractiveTutorial';

// Normaliza para busca sem acentos / maiúsculas.
const norm = (s: string) =>
  s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

function matches(topic: HelpTopic, q: string): boolean {
  if (!q) return true;
  const haystack = norm(
    [topic.title, topic.what, topic.how, topic.when, ...(topic.keywords || [])].join(' '),
  );
  return norm(q).split(/\s+/).filter(Boolean).every((term) => haystack.includes(term));
}

export const HelpPage: React.FC = () => {
  const { user } = useAuth();
  const [query, setQuery] = useState('');
  const [openId, setOpenId] = useState<string | null>(null);

  const topics = useMemo(() => getHelpTopics(user?.role), [user?.role]);
  const filtered = useMemo(() => topics.filter((t) => matches(t, query)), [topics, query]);

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      {/* Cabeçalho */}
      <div className="flex items-center gap-2">
        <HelpCircle className="w-6 h-6 text-accent-neon shrink-0" />
        <div>
          <h1 className="text-xl font-bold">Ajuda</h1>
          <p className="text-xs text-text-muted">Entenda cada funcionalidade do Tenfy.</p>
        </div>
      </div>

      {/* Busca */}
      <div className="relative">
        <Search className="w-4 h-4 text-text-muted absolute left-3 top-1/2 -translate-y-1/2" />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Buscar por palavra-chave (ex.: inscrição, pix, ranking)…"
          className="input-base w-full text-sm !pl-9"
        />
      </div>

      {/* Rever tutorial */}
      <button
        onClick={() => window.dispatchEvent(new Event(OPEN_TUTORIAL_EVENT))}
        className="btn-secondary !text-sm flex items-center gap-2"
      >
        <PlayCircle className="w-4 h-4" /> Rever tutorial de primeiros passos
      </button>

      {/* Tópicos */}
      {filtered.length === 0 ? (
        <div className="card text-center py-10 text-sm text-text-muted">
          Nada encontrado para “{query}”. Tente outra palavra-chave.
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((topic) => {
            const Icon = topic.icon;
            const isOpen = openId === topic.id;
            return (
              <div key={topic.id} className="card !p-0 overflow-hidden">
                <button
                  onClick={() => setOpenId(isOpen ? null : topic.id)}
                  className="w-full flex items-center gap-3 px-4 py-3 text-left"
                  aria-expanded={isOpen}
                >
                  <div className="w-9 h-9 rounded-lg bg-accent-neon/10 flex items-center justify-center shrink-0">
                    <Icon className="w-4 h-4 text-accent-neon" />
                  </div>
                  <span className="flex-1 text-sm font-semibold">{topic.title}</span>
                  <ChevronDown className={`w-4 h-4 text-text-muted transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                </button>
                {isOpen && (
                  <div className="px-4 pb-4 pt-1 space-y-3 text-sm text-text-secondary border-t border-border-subtle">
                    <div>
                      <div className="text-[11px] font-bold uppercase tracking-wide text-text-muted mt-3 mb-0.5">O que é</div>
                      <p className="leading-relaxed">{topic.what}</p>
                    </div>
                    <div>
                      <div className="text-[11px] font-bold uppercase tracking-wide text-text-muted mb-0.5">Como usar</div>
                      <p className="leading-relaxed">{topic.how}</p>
                    </div>
                    <div>
                      <div className="text-[11px] font-bold uppercase tracking-wide text-text-muted mb-0.5">Quando usar</div>
                      <p className="leading-relaxed">{topic.when}</p>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
