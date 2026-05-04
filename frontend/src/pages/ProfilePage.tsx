import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader2, Trash2, Mail, Edit2, CheckCircle2, Camera, AlertTriangle } from 'lucide-react';
import toast from 'react-hot-toast';
import { useAuth } from '../contexts/AuthContext';
import { PlayerProfile } from '../types';
import { listProfiles, setPrimary, deleteProfile, updateProfile } from '../services/data';
import { deleteAccount, uploadAvatar } from '../services/auth';
import { extractApiError, mediaUrl } from '../services/api';

// ─── Confirm Modal ────────────────────────────────────────────────────────────

interface ConfirmModalProps {
  title: string;
  message: string;
  confirmLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

const ConfirmModal: React.FC<ConfirmModalProps> = ({
  title, message, confirmLabel = 'Confirmar', danger = false, onConfirm, onCancel,
}) => (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
    <div className="bg-bg-card border border-border rounded-xl shadow-xl w-full max-w-sm p-6 space-y-4">
      <div className="flex items-start gap-3">
        {danger && <AlertTriangle className="w-5 h-5 text-status-canceled mt-0.5 shrink-0" />}
        <div>
          <h2 className="font-semibold text-base">{title}</h2>
          <p className="text-sm text-text-secondary mt-1">{message}</p>
        </div>
      </div>
      <div className="flex gap-2 justify-end">
        <button className="btn-secondary" onClick={onCancel}>Cancelar</button>
        <button
          className={danger ? 'btn-primary !bg-status-canceled !border-status-canceled/60' : 'btn-primary'}
          onClick={onConfirm}
        >
          {confirmLabel}
        </button>
      </div>
    </div>
  </div>
);

// ─── Main Page ────────────────────────────────────────────────────────────────

export const ProfilePage: React.FC = () => {
  const { user, setUser, logout } = useAuth();
  const [profiles, setProfiles] = useState<PlayerProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<number | null>(null);
  const [confirmRemove, setConfirmRemove] = useState<number | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function load() {
    setLoading(true);
    try {
      const data = await listProfiles();
      setProfiles(data);
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function makePrimary(id: number) {
    try {
      await setPrimary(id);
      toast.success('Perfil principal atualizado');
      load();
    } catch (err) { toast.error(extractApiError(err)); }
  }

  async function handleRemoveConfirmed() {
    if (confirmRemove == null) return;
    try {
      await deleteProfile(confirmRemove);
      toast.success('Perfil removido');
      load();
    } catch (err) { toast.error(extractApiError(err)); }
    finally { setConfirmRemove(null); }
  }

  async function handleDeleteAccountConfirmed() {
    setConfirmDelete(false);
    try {
      await deleteAccount();
      toast.success('Conta removida');
      await logout();
    } catch (err) { toast.error(extractApiError(err)); }
  }

  async function handleAvatarChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingAvatar(true);
    try {
      const updated = await uploadAvatar(file);
      setUser(updated);
      toast.success('Foto atualizada');
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setUploadingAvatar(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  const avatarLetter = (user?.full_name || user?.email || 'U').slice(0, 1).toUpperCase();

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Perfil</h1>

      {/* User card */}
      <div className="card">
        <div className="flex items-center gap-4">
          {/* Avatar with upload overlay */}
          <div className="relative shrink-0">
            <div className="w-14 h-14 rounded-full bg-accent-neon/20 text-accent-neon flex items-center justify-center text-xl font-bold overflow-hidden">
              {user?.avatar ? (
                <img src={mediaUrl(user.avatar)} alt="avatar" className="w-full h-full object-cover" />
              ) : (
                avatarLetter
              )}
            </div>
            <button
              className="absolute bottom-0 right-0 w-6 h-6 rounded-full bg-bg-card border border-border flex items-center justify-center hover:bg-bg-elevated transition-colors"
              title="Alterar foto"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploadingAvatar}
            >
              {uploadingAvatar
                ? <Loader2 className="w-3.5 h-3.5 animate-spin text-accent-neon" />
                : <Camera className="w-3.5 h-3.5 text-text-secondary" />}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleAvatarChange}
            />
          </div>

          <div className="min-w-0 flex-1">
            <div className="font-semibold truncate">{user?.full_name || '—'}</div>
            <div className="text-xs text-text-muted flex items-center gap-1">
              <Mail className="w-3 h-3" /> {user?.email}
            </div>
          </div>
          {user?.is_staff && (
            <span className="badge bg-accent-blue/15 text-accent-blue border border-accent-blue/30">
              Admin
            </span>
          )}
        </div>
      </div>

      {/* Sports profiles */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h2 className="font-semibold">Perfis esportivos</h2>
          {user?.role !== 'player' && (
            <Link to="/onboarding" className="text-xs text-accent-blue hover:underline">
              + Novo
            </Link>
          )}
        </div>
        {loading ? (
          <div className="py-8 flex justify-center">
            <Loader2 className="w-6 h-6 text-accent-neon animate-spin" />
          </div>
        ) : profiles.length === 0 ? (
          <div className="card text-center py-6 text-sm text-text-muted">
            Nenhum perfil criado.{' '}
            <Link to="/onboarding" className="text-accent-neon hover:underline">Criar agora</Link>
          </div>
        ) : (
          <div className="space-y-2">
            {profiles.map((p) =>
              editing === p.id ? (
                <ProfileEditor
                  key={p.id}
                  profile={p}
                  onSaved={() => { setEditing(null); load(); }}
                  onCancel={() => setEditing(null)}
                />
              ) : (
                <div key={p.id} className="card">
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold">{p.display_name}</h3>
                        {p.is_primary && (
                          <span className="badge bg-accent-neon/15 text-accent-neon border border-accent-neon/30">
                            <CheckCircle2 className="w-3 h-3" /> Principal
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-text-secondary mt-1 space-y-0.5">
                        {p.birth_year && <div>Nascimento: {p.birth_year} (idade esportiva: {p.sporting_age})</div>}
                        {p.gender && <div>Gênero: {p.gender === 'M' ? 'Masculino' : 'Feminino'}</div>}
                        {p.tennis_class && <div>Classe: {p.tennis_class}</div>}
                        {p.home_state && <div>Local: {p.home_city ? `${p.home_city}/` : ''}{p.home_state} (raio {p.travel_radius_km}km)</div>}
                        <div>Nível: {p.competitive_level}</div>
                      </div>
                    </div>
                    <div className="flex flex-col gap-1">
                      <button
                        className="btn-ghost !p-1.5"
                        title="Editar"
                        onClick={() => setEditing(p.id)}
                      >
                        <Edit2 className="w-4 h-4" />
                      </button>
                      {user?.role !== 'player' && (
                        <button
                          className="btn-ghost !p-1.5 text-status-canceled"
                          title="Remover"
                          onClick={() => setConfirmRemove(p.id)}
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </div>
                  {!p.is_primary && (
                    <button
                      className="text-xs text-accent-blue hover:underline mt-2"
                      onClick={() => makePrimary(p.id)}
                    >
                      Tornar principal
                    </button>
                  )}
                </div>
              ),
            )}
          </div>
        )}
      </div>

      {/* Privacy / delete account */}
      <div className="card">
        <h2 className="font-semibold mb-2">Sua privacidade</h2>
        <p className="text-xs text-text-secondary mb-3">
          Você pode solicitar a exclusão da sua conta e seus dados a qualquer momento (LGPD).
        </p>
        <button
          className="btn-secondary !text-status-canceled !border-status-canceled/30"
          onClick={() => setConfirmDelete(true)}
        >
          Excluir minha conta
        </button>
      </div>

      {/* Modals */}
      {confirmRemove != null && (
        <ConfirmModal
          title="Remover perfil"
          message="Este perfil será excluído permanentemente. Deseja continuar?"
          confirmLabel="Remover"
          danger
          onConfirm={handleRemoveConfirmed}
          onCancel={() => setConfirmRemove(null)}
        />
      )}

      {confirmDelete && (
        <ConfirmModal
          title="Excluir conta"
          message="Todos os seus dados serão removidos permanentemente conforme a LGPD. Esta ação não pode ser desfeita."
          confirmLabel="Excluir conta"
          danger
          onConfirm={handleDeleteAccountConfirmed}
          onCancel={() => setConfirmDelete(false)}
        />
      )}
    </div>
  );
};

// ─── Profile Editor ───────────────────────────────────────────────────────────

const ProfileEditor: React.FC<{
  profile: PlayerProfile;
  onSaved: () => void;
  onCancel: () => void;
}> = ({ profile, onSaved, onCancel }) => {
  const [form, setForm] = useState({
    display_name: profile.display_name,
    birth_year: profile.birth_year || '',
    gender: profile.gender,
    home_state: profile.home_state,
    home_city: profile.home_city,
    travel_radius_km: profile.travel_radius_km,
    tennis_class: profile.tennis_class,
    competitive_level: profile.competitive_level,
  });
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      await updateProfile(profile.id, {
        ...form,
        birth_year: form.birth_year ? Number(form.birth_year) : null,
      } as any);
      toast.success('Perfil atualizado');
      onSaved();
    } catch (err) { toast.error(extractApiError(err)); }
    finally { setSaving(false); }
  }

  return (
    <div className="card space-y-3">
      <input className="input-base" value={form.display_name}
        onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
      <div className="grid grid-cols-2 gap-2">
        <input className="input-base" type="number" placeholder="Ano nasc." value={form.birth_year}
          onChange={(e) => setForm({ ...form, birth_year: e.target.value as any })} />
        <select className="input-base" value={form.gender}
          onChange={(e) => setForm({ ...form, gender: e.target.value as any })}>
          <option value="">Gênero</option>
          <option value="M">M</option><option value="F">F</option>
        </select>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <input className="input-base" placeholder="UF" maxLength={2} value={form.home_state}
          onChange={(e) => setForm({ ...form, home_state: e.target.value.toUpperCase() })} />
        <input className="input-base" placeholder="Cidade" value={form.home_city}
          onChange={(e) => setForm({ ...form, home_city: e.target.value })} />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <select className="input-base" value={form.tennis_class}
          onChange={(e) => setForm({ ...form, tennis_class: e.target.value })}>
          <option value="">Classe</option>
          {['1','2','3','4','5','PR'].map((c) => <option key={c} value={c}>{c === 'PR' ? 'Princ.' : c}</option>)}
        </select>
        <select className="input-base" value={form.competitive_level}
          onChange={(e) => setForm({ ...form, competitive_level: e.target.value as any })}>
          <option value="beginner">Principiante</option>
          <option value="amateur">Amador</option>
          <option value="federated">Federado</option>
          <option value="youth">Juvenil</option>
          <option value="pro">Pro</option>
        </select>
      </div>
      <div className="flex gap-2">
        <button className="btn-secondary flex-1" onClick={onCancel}>Cancelar</button>
        <button className="btn-primary flex-1" onClick={save} disabled={saving}>
          {saving ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : 'Salvar'}
        </button>
      </div>
    </div>
  );
};
