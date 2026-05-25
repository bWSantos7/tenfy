import React, { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { StateMultiSelect, loadCitiesForState, ALL_UFS } from '../components/StateMultiSelect';
import {
  Loader2, Trash2, Mail, Edit2, CheckCircle2, Camera, AlertTriangle,
  Sun, Moon, CreditCard, Ticket, Users, ShieldCheck, Bell, LogOut,
  MapPin, Trophy, Calendar, User, ChevronRight, Shield, Download, Plus, Eye, EyeOff, Star,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import { ParentChild, PlayerProfile } from '../types';
import { listProfiles, setPrimary, deleteProfile, updateProfile, requestDataExport, listChildren, removeChild, createChildWithProfile } from '../services/data';
import { deleteAccount, uploadAvatar, linkExistingChild } from '../services/auth';
import { extractApiError, mediaUrl } from '../services/api';
import { LEVEL_LABELS, GENDER_LABELS, TENNIS_CLASS_LABELS, ROLE_LABELS } from '../utils/format';
import { getProfileModality, setProfileModality, MODALITY_OPTIONS } from '../utils/profileModality';

// ─── Confirm Modal ─────────────────────────────────────────────────────────────

const ConfirmModal: React.FC<{
  title: string; message: string; confirmLabel?: string; danger?: boolean;
  onConfirm: () => void; onCancel: () => void;
}> = ({ title, message, confirmLabel = 'Confirmar', danger = false, onConfirm, onCancel }) => (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
    <div className="bg-bg-card border border-border-subtle rounded-2xl shadow-xl w-full max-w-sm p-6 space-y-4">
      <div className="flex items-start gap-3">
        {danger && <AlertTriangle className="w-5 h-5 text-red-400 mt-0.5 shrink-0" />}
        <div>
          <h2 className="font-semibold text-base">{title}</h2>
          <p className="text-sm text-text-secondary mt-1">{message}</p>
        </div>
      </div>
      <div className="flex gap-2 justify-end">
        <button className="btn-secondary" onClick={onCancel}>Cancelar</button>
        <button
          className={danger ? 'btn-primary !bg-red-500 !border-red-500/60 shadow-none' : 'btn-primary'}
          onClick={onConfirm}
        >{confirmLabel}</button>
      </div>
    </div>
  </div>
);

// ─── Main Page ─────────────────────────────────────────────────────────────────

export const ProfilePage: React.FC = () => {
  const { user, setUser, logout } = useAuth();
  const { theme, toggle: toggleTheme } = useTheme();
  const navigate = useNavigate();
  const [profiles, setProfiles] = useState<PlayerProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<PlayerProfile | null>(null);
  const [confirmRemove, setConfirmRemove] = useState<number | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  const [exporting, setExporting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Dependentes
  const [children, setChildren] = useState<ParentChild[]>([]);
  const [loadingChildren, setLoadingChildren] = useState(false);
  const [showAddChild, setShowAddChild] = useState(false);
  const [confirmRemoveChild, setConfirmRemoveChild] = useState<number | null>(null);

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

  async function loadChildren() {
    setLoadingChildren(true);
    try {
      const data = await listChildren();
      setChildren(data);
    } catch {
      // silently ignore if endpoint not available
    } finally {
      setLoadingChildren(false);
    }
  }

  useEffect(() => { load(); }, []);

  useEffect(() => {
    if (user?.role === 'parent') loadChildren();
  }, [user?.role]);

  async function makePrimary(id: number) {
    try { await setPrimary(id); toast.success('Perfil principal atualizado'); load(); }
    catch (err) { toast.error(extractApiError(err)); }
  }

  async function handleRemoveConfirmed() {
    if (confirmRemove == null) return;
    try { await deleteProfile(confirmRemove); toast.success('Perfil removido'); load(); }
    catch (err) { toast.error(extractApiError(err)); }
    finally { setConfirmRemove(null); }
  }

  async function handleDeleteAccountConfirmed() {
    setConfirmDelete(false);
    try { await deleteAccount(); toast.success('Conta removida'); setUser(null); }
    catch (err) { toast.error(extractApiError(err)); }
  }

  async function handleAvatarChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingAvatar(true);
    try { const updated = await uploadAvatar(file); setUser(updated); toast.success('Foto atualizada'); }
    catch (err) { toast.error(extractApiError(err)); }
    finally { setUploadingAvatar(false); if (fileInputRef.current) fileInputRef.current.value = ''; }
  }

  async function handleRemoveChildConfirmed() {
    if (confirmRemoveChild == null) return;
    try { await removeChild(confirmRemoveChild); toast.success('Dependente removido'); loadChildren(); }
    catch (err) { toast.error(extractApiError(err)); }
    finally { setConfirmRemoveChild(null); }
  }

  async function handleExport() {
    setExporting(true);
    try {
      const data = await requestDataExport();
      const json = JSON.stringify(data, null, 2);
      const blob = new Blob([json], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'meus-dados-tenfy.json';
      a.click();
      URL.revokeObjectURL(url);
      toast.success('Dados exportados com sucesso.');
    } catch {
      toast.error('Não foi possível exportar os dados.');
    } finally { setExporting(false); }
  }

  const avatarLetter = (user?.full_name || user?.email || 'U').slice(0, 1).toUpperCase();
  const roleLabel = ROLE_LABELS[user?.role ?? ''] ?? user?.role ?? '';

  return (
    <div className="space-y-4 pb-4">

      {/* ─── User card (igual ao mobile) ──────────────────────────────────── */}
      <div className="card">
        <div className="flex items-center gap-4">
          {/* Avatar com câmera */}
          <div className="relative shrink-0">
            <div className="w-16 h-16 rounded-full bg-accent-neon/20 flex items-center justify-center text-xl font-bold overflow-hidden border-2 border-accent-neon/40">
              {user?.avatar
                ? <img src={mediaUrl(user.avatar)} alt="avatar" className="w-full h-full object-cover" />
                : <span className="text-accent-neon text-2xl font-bold">{avatarLetter}</span>}
            </div>
            <button
              className="absolute bottom-0 right-0 w-6 h-6 rounded-full bg-accent-neon flex items-center justify-center border-2 border-bg-base hover:opacity-90 transition-opacity"
              title="Alterar foto"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploadingAvatar}
              style={{ color: 'rgb(var(--btn-text))' }}
            >
              {uploadingAvatar ? <Loader2 className="w-3 h-3 animate-spin" /> : <Camera className="w-3 h-3" />}
            </button>
            <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={handleAvatarChange} />
          </div>

          <div className="flex-1 min-w-0">
            <div className="font-bold text-lg truncate">{user?.full_name || '—'}</div>
            <div className="text-xs text-text-muted flex items-center gap-1 mt-0.5">
              <Mail className="w-3 h-3" /> {user?.email}
            </div>
            <div className="flex items-center gap-2 mt-2 flex-wrap">
              <span className="text-xs font-semibold px-2 py-0.5 rounded-lg bg-accent-blue/20 text-accent-blue">
                {roleLabel}
              </span>
              {user?.is_staff && (
                <span className="text-xs font-semibold px-2 py-0.5 rounded-lg bg-accent-neon/20 text-accent-neon">
                  Staff
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ─── Meu responsável (só para contas gerenciadas) ─────────────────── */}
      {user?.managed_by_parent && user?.parent_info && (
        <div className="card space-y-3">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-accent-blue" />
            <h2 className="font-bold text-sm">Meu responsável</h2>
          </div>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-accent-blue/15 flex items-center justify-center shrink-0">
              <span className="text-accent-blue font-bold text-base">
                {(user.parent_info.full_name || 'R').slice(0, 1).toUpperCase()}
              </span>
            </div>
            <div>
              <div className="font-semibold text-sm">{user.parent_info.full_name || '—'}</div>
              <div className="text-xs text-text-muted">{user.parent_info.email}</div>
            </div>
          </div>
        </div>
      )}

      {/* ─── Configurações da conta (menu igual ao mobile) ────────────────── */}
      <div className="card space-y-0 !p-0 overflow-hidden">
        <div className="px-4 py-3 border-b border-border-subtle">
          <h2 className="font-bold text-sm">Configurações da conta</h2>
        </div>

        {/* Tema claro/escuro */}
        <button onClick={toggleTheme} className="menu-row w-full px-4 text-left">
          {theme === 'dark'
            ? <Sun className="w-4 h-4 text-text-muted shrink-0" />
            : <Moon className="w-4 h-4 text-text-muted shrink-0" />}
          <span className="flex-1 text-sm">{theme === 'dark' ? 'Ativar modo claro' : 'Ativar modo escuro'}</span>
          <ChevronRight className="w-4 h-4 text-text-muted" />
        </button>

        {/* Assinatura — não exibir para contas gerenciadas */}
        {!user?.managed_by_parent && (
          <Link to="/assinatura" className="menu-row px-4 flex items-center gap-3">
            <CreditCard className="w-4 h-4 text-text-muted shrink-0" />
            <span className="flex-1 text-sm">Minha assinatura</span>
            <ChevronRight className="w-4 h-4 text-text-muted" />
          </Link>
        )}

        {/* Inscrições */}
        <Link to="/inscricoes" className="menu-row px-4 flex items-center gap-3">
          <Ticket className="w-4 h-4 text-text-muted shrink-0" />
          <span className="flex-1 text-sm">Minhas inscrições</span>
          <ChevronRight className="w-4 h-4 text-text-muted" />
        </Link>

        {/* Alertas */}
        <Link to="/alertas" className="menu-row px-4 flex items-center gap-3">
          <Bell className="w-4 h-4 text-text-muted shrink-0" />
          <span className="flex-1 text-sm">Notificações e alertas</span>
          <ChevronRight className="w-4 h-4 text-text-muted" />
        </Link>

        {/* Watchlist */}
        <Link to="/watchlist" className="menu-row px-4 flex items-center gap-3">
          <Star className="w-4 h-4 text-text-muted shrink-0" />
          <span className="flex-1 text-sm">Minha agenda</span>
          <ChevronRight className="w-4 h-4 text-text-muted" />
        </Link>

        {/* Coach */}
        {user?.role === 'coach' && (
          <Link to="/treinador" className="menu-row px-4 flex items-center gap-3">
            <Users className="w-4 h-4 text-text-muted shrink-0" />
            <span className="flex-1 text-sm">Meus alunos</span>
            <ChevronRight className="w-4 h-4 text-text-muted" />
          </Link>
        )}

        {/* Admin */}
        {user?.is_staff && (
          <Link to="/admin-panel" className="menu-row px-4 flex items-center gap-3">
            <ShieldCheck className="w-4 h-4 text-text-muted shrink-0" />
            <span className="flex-1 text-sm">Painel administrativo</span>
            <ChevronRight className="w-4 h-4 text-text-muted" />
          </Link>
        )}

        {/* Logout */}
        <button
          onClick={async () => { await logout(); navigate('/login', { replace: true }); }}
          className="menu-row w-full px-4 text-left border-b-0 !text-red-400 hover:!text-red-400"
        >
          <LogOut className="w-4 h-4 shrink-0" />
          <span className="flex-1 text-sm">Sair da conta</span>
        </button>
      </div>

      {/* ─── Perfis esportivos ─────────────────────────────────────────────── */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="font-bold">Perfil esportivo</h2>
            <p className="text-xs text-text-muted mt-0.5">
              {user?.managed_by_parent ? 'Seu perfil de jogador (gerenciado pelo responsável)' : 'Gerencie seu perfil de jogador'}
            </p>
          </div>
          {!user?.managed_by_parent && (
            <Link
              to="/onboarding"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold text-accent-neon bg-accent-neon/10 border border-accent-neon/30 hover:bg-accent-neon/20 transition-colors"
            >
              + {profiles.length === 0 ? 'Criar' : 'Novo'}
            </Link>
          )}
        </div>

        {loading ? (
          <div className="py-8 flex justify-center"><Loader2 className="w-6 h-6 text-accent-neon animate-spin" /></div>
        ) : profiles.length === 0 ? (
          <div className="card text-center py-8 space-y-2">
            <User className="w-8 h-8 text-text-muted mx-auto" />
            <p className="text-sm text-text-muted">Nenhum perfil criado.</p>
            <Link to="/onboarding" className="text-sm text-accent-neon hover:underline font-medium">Criar agora</Link>
          </div>
        ) : (
          <div className="space-y-3">
            {profiles.map((p) =>
              editing?.id === p.id ? (
                <ProfileEditor
                  key={p.id}
                  profile={p}
                  onSaved={() => { setEditing(null); load(); }}
                  onCancel={() => setEditing(null)}
                />
              ) : (
                <ProfileCard
                  key={p.id}
                  profile={p}
                  onEdit={() => setEditing(p)}
                  onMakePrimary={() => makePrimary(p.id)}
                  onRemove={() => setConfirmRemove(p.id)}
                  readOnly={!!user?.managed_by_parent}
                />
              )
            )}
          </div>
        )}
      </div>

      {/* ─── Meus dependentes (só para role parent) ───────────────────────── */}
      {user?.role === 'parent' && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <div>
              <h2 className="font-bold">Meus dependentes — Perfil esportivo</h2>
              <p className="text-xs text-text-muted mt-0.5">Gerencie os dependentes e seus perfis de jogador</p>
            </div>
            <button
              onClick={() => setShowAddChild((v) => !v)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold text-accent-neon bg-accent-neon/10 border border-accent-neon/30 hover:bg-accent-neon/20 transition-colors"
            >
              <Plus className="w-3.5 h-3.5" /> Novo
            </button>
          </div>

          {showAddChild && (
            <AddChildForm
              onAdded={() => { setShowAddChild(false); loadChildren(); }}
              onCancel={() => setShowAddChild(false)}
            />
          )}

          {loadingChildren ? (
            <div className="py-6 flex justify-center"><Loader2 className="w-5 h-5 text-accent-neon animate-spin" /></div>
          ) : children.length === 0 && !showAddChild ? (
            <div className="card text-center py-8 space-y-2">
              <Users className="w-8 h-8 text-text-muted mx-auto" />
              <p className="text-sm text-text-muted">Nenhum dependente cadastrado.</p>
              <button onClick={() => setShowAddChild(true)} className="text-sm text-accent-neon hover:underline font-medium">Adicionar agora</button>
            </div>
          ) : (
            <div className="space-y-3">
              {children.map((c) => (
                <div key={c.id} className="card flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-9 h-9 rounded-full bg-accent-neon/15 flex items-center justify-center shrink-0">
                      <User className="w-4 h-4 text-accent-neon" />
                    </div>
                    <div className="min-w-0">
                      <div className="font-semibold text-sm truncate">{c.child_detail.full_name || '—'}</div>
                      <div className="text-xs text-text-muted truncate">{c.child_detail.email}</div>
                    </div>
                  </div>
                  <button
                    onClick={() => setConfirmRemoveChild(c.id)}
                    className="shrink-0 p-1.5 rounded-lg bg-bg-elevated hover:bg-red-500/15 text-text-muted hover:text-red-400 transition-colors"
                    title="Remover dependente"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ─── Privacidade e dados (LGPD) — igual ao mobile ─────────────────── */}
      <div className="card space-y-3">
        <div className="flex items-center gap-2">
          <Shield className="w-4 h-4 text-text-muted" />
          <h2 className="font-bold text-sm">Privacidade e dados (LGPD)</h2>
        </div>
        <p className="text-xs text-text-secondary">
          Conforme a LGPD, você pode exportar ou excluir todos os seus dados a qualquer momento.
        </p>
        <button
          className="btn-secondary w-full flex items-center justify-center gap-2 !text-sm"
          onClick={handleExport}
          disabled={exporting}
        >
          {exporting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
          Exportar meus dados
        </button>
        <button
          className="btn-primary w-full !text-sm !bg-red-500 !border-red-500/60 shadow-none hover:!bg-red-600"
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
      {confirmRemoveChild != null && (
        <ConfirmModal
          title="Remover dependente"
          message="O vínculo com este dependente será removido. Deseja continuar?"
          confirmLabel="Remover"
          danger
          onConfirm={handleRemoveChildConfirmed}
          onCancel={() => setConfirmRemoveChild(null)}
        />
      )}
    </div>
  );
};

// ─── ProfileCard — cards com ícones (igual ao mobile) ─────────────────────────

const ProfileCard: React.FC<{
  profile: PlayerProfile;
  onEdit: () => void;
  onMakePrimary: () => void;
  onRemove: () => void;
  readOnly?: boolean;
}> = ({ profile: p, onEdit, onMakePrimary, onRemove, readOnly = false }) => {
  const levelLabel = LEVEL_LABELS[p.competitive_level] ?? p.competitive_level;
  const classLabel = p.tennis_class ? (TENNIS_CLASS_LABELS[p.tennis_class] ?? `Classe ${p.tennis_class}`) : null;
  const genderLabel = p.gender ? (GENDER_LABELS[p.gender] ?? p.gender) : null;

  return (
    <div className="card space-y-3">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2 flex-wrap">
          <h3 className="font-bold text-base">{p.display_name}</h3>
          {p.is_primary && (
            <span className="flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded-lg bg-accent-neon/15 text-accent-neon border border-accent-neon/30">
              <CheckCircle2 className="w-3 h-3" /> Principal
            </span>
          )}
        </div>
        {!readOnly && (
          <button className="btn-ghost !p-1.5" onClick={onEdit} title="Editar">
            <Edit2 className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Rows com ícones — igual ao mobile ProfileCard */}
      <div className="space-y-1.5">
        {(p.birth_year || p.sporting_age) && (
          <div className="flex items-center gap-2 text-xs text-text-secondary">
            <Calendar className="w-3.5 h-3.5 text-text-muted shrink-0" />
            <span>
              {p.birth_year ? `Nascimento: ${p.birth_year}` : ''}
              {p.sporting_age ? ` • ${p.sporting_age} anos esportivos` : ''}
            </span>
          </div>
        )}
        {genderLabel && (
          <div className="flex items-center gap-2 text-xs text-text-secondary">
            <User className="w-3.5 h-3.5 text-text-muted shrink-0" />
            <span>{genderLabel}</span>
          </div>
        )}
        {(p.home_city || p.home_state) && (
          <div className="flex items-center gap-2 text-xs text-text-secondary">
            <MapPin className="w-3.5 h-3.5 text-text-muted shrink-0" />
            <span>{[p.home_city, p.home_state].filter(Boolean).join(' / ')}</span>
            {p.travel_radius_km && <span className="text-text-muted">• raio {p.travel_radius_km} km</span>}
          </div>
        )}
        <div className="flex items-center gap-2 text-xs text-text-secondary">
          <Trophy className="w-3.5 h-3.5 text-text-muted shrink-0" />
          <span>{levelLabel}{classLabel ? ` • ${classLabel}` : ''}</span>
        </div>
      </div>

      {!readOnly && (
        <div className="flex gap-2 pt-1">
          <button className="btn-secondary flex-1 !text-sm !py-2" onClick={onEdit}>Editar</button>
          {!p.is_primary && (
            <button className="btn-ghost flex-1 !text-sm !py-2 border border-border-subtle" onClick={onMakePrimary}>Selecionar</button>
          )}
          <button className="btn-primary flex-1 !text-sm !py-2 !bg-red-500 !border-red-500/60 shadow-none hover:!bg-red-600" onClick={onRemove}>
            <Trash2 className="w-3.5 h-3.5 inline mr-1" />Remover
          </button>
        </div>
      )}
    </div>
  );
};

// ─── ProfileEditor — edição completa com states multiselect ──────────────────

const UF_OPTIONS_EDITOR = [
  'AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB',
  'PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO',
];

const ProfileEditor: React.FC<{
  profile: PlayerProfile;
  onSaved: () => void;
  onCancel: () => void;
}> = ({ profile, onSaved, onCancel }) => {
  const [form, setForm] = useState({
    display_name:      profile.display_name,
    birth_year:        profile.birth_year ? String(profile.birth_year) : '',
    gender:            profile.gender ?? '' as '' | 'M' | 'F',
    home_state:        profile.home_state ?? 'SP',
    home_city:         profile.home_city ?? '',
    travel_states:     profile.travel_states ?? [],
    tennis_class:      profile.tennis_class ?? '',
    competitive_level: profile.competitive_level ?? 'amateur',
  });
  const [modality, setModality] = useState(() => getProfileModality(profile.id));
  const [saving, setSaving] = useState(false);
  const [cities, setCities] = useState<{ value: string; label: string }[]>([]);
  const [loadingCities, setLoadingCities] = useState(false);

  useEffect(() => {
    setLoadingCities(true);
    loadCitiesForState(form.home_state)
      .then(setCities)
      .finally(() => setLoadingCities(false));
  }, [form.home_state]);

  async function save() {
    setSaving(true);
    try {
      await updateProfile(profile.id, {
        ...form,
        birth_year: form.birth_year ? Number(form.birth_year) : null,
        preferred_modality: modality,
      } as any);
      setProfileModality(profile.id, modality);
      toast.success('Perfil atualizado');
      onSaved();
    } catch (err) { toast.error(extractApiError(err)); }
    finally { setSaving(false); }
  }

  return (
    <div className="card space-y-3">
      <h3 className="font-bold text-sm text-text-muted">Editando: {profile.display_name}</h3>

      <div>
        <label className="text-xs text-text-secondary mb-1 block">Nome de exibição</label>
        <input className="input-base" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="text-xs text-text-secondary mb-1 block">Ano nasc.</label>
          <input className="input-base" type="number" placeholder="1990" value={form.birth_year}
            onChange={(e) => setForm({ ...form, birth_year: e.target.value })} />
        </div>
        <div>
          <label className="text-xs text-text-secondary mb-1 block">Gênero</label>
          <select className="input-base" value={form.gender}
            onChange={(e) => setForm({ ...form, gender: e.target.value as '' | 'M' | 'F' })}>
            <option value="">—</option>
            <option value="M">Masculino</option>
            <option value="F">Feminino</option>
          </select>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <div>
          <label className="text-xs text-text-secondary mb-1 block">UF</label>
          <select className="input-base" value={form.home_state}
            onChange={(e) => setForm({ ...form, home_state: e.target.value, home_city: '' })}>
            {UF_OPTIONS_EDITOR.map((uf) => <option key={uf} value={uf}>{uf}</option>)}
          </select>
        </div>
        <div className="col-span-2">
          <label className="text-xs text-text-secondary mb-1 block">Cidade</label>
          {cities.length > 0 ? (
            <select className="input-base" value={form.home_city}
              onChange={(e) => setForm({ ...form, home_city: e.target.value })}>
              <option value="">{loadingCities ? 'Carregando...' : 'Selecione'}</option>
              {cities.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
          ) : (
            <input className="input-base" placeholder={loadingCities ? 'Carregando...' : 'Cidade'} value={form.home_city}
              onChange={(e) => setForm({ ...form, home_city: e.target.value })} />
          )}
        </div>
      </div>

      {/* Estados onde aceita jogar — sem raio de km */}
      <StateMultiSelect
        values={form.travel_states}
        onChange={(vals) => setForm({ ...form, travel_states: vals })}
      />

      <div>
        <label className="text-xs text-text-secondary mb-1 block">Modalidade principal</label>
        <select className="input-base" value={modality} onChange={(e) => setModality(e.target.value)}>
          {MODALITY_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <p className="text-[10px] text-text-muted mt-0.5">Usado para filtrar torneios compatíveis</p>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="text-xs text-text-secondary mb-1 block">Nível</label>
          <select className="input-base" value={form.competitive_level}
            onChange={(e) => setForm({ ...form, competitive_level: e.target.value as any })}>
            {Object.entries(LEVEL_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-text-secondary mb-1 block">Classe (FPT/CBT)</label>
          <select className="input-base" value={form.tennis_class}
            onChange={(e) => setForm({ ...form, tennis_class: e.target.value })}>
            <option value="">Sem classe</option>
            {Object.entries(TENNIS_CLASS_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
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

// ─── AddChildForm — Novo dependente (igual ao mobile) ─────────────────────────

const UF_OPTIONS = ALL_UFS;

const AddChildForm: React.FC<{
  onAdded: () => void;
  onCancel: () => void;
}> = ({ onAdded, onCancel }) => {
  const [account, setAccount] = useState({
    full_name: '',
    email: '',
    password: '',
    confirm_password: '',
  });
  const [profile, setProfile] = useState({
    display_name: '',
    birth_year: '',
    gender: '' as '' | 'M' | 'F',
    home_state: 'SP',
    home_city: '',
    travel_states: [] as string[],
    competitive_level: 'amateur',
    tennis_class: '',
    preferred_modality: 'tennis',
  });
  const [showPwd, setShowPwd] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [cities, setCities] = useState<{ value: string; label: string }[]>([]);
  const [loadingCities, setLoadingCities] = useState(false);
  // TC-013/014: link existing account flow
  const [duplicateEmailDetected, setDuplicateEmailDetected] = useState(false);

  useEffect(() => {
    setLoadingCities(true);
    loadCitiesForState(profile.home_state)
      .then(setCities)
      .finally(() => setLoadingCities(false));
  }, [profile.home_state]);

  function isEmailDuplicateError(err: unknown): boolean {
    const msg = extractApiError(err).toLowerCase();
    return msg.includes('email') && (msg.includes('existe') || msg.includes('already') || msg.includes('cadastro') || msg.includes('used'));
  }

  async function handleSubmit() {
    if (!account.full_name.trim()) { toast.error('Informe o nome completo.'); return; }
    if (!account.email.trim()) { toast.error('Informe o e-mail.'); return; }
    if (account.password.length < 8) { toast.error('Senha deve ter pelo menos 8 caracteres.'); return; }
    if (account.password !== account.confirm_password) { toast.error('As senhas não conferem.'); return; }
    if (!profile.birth_year) { toast.error('Informe o ano de nascimento.'); return; }
    setSaving(true);
    setDuplicateEmailDetected(false);
    try {
      await createChildWithProfile(
        { full_name: account.full_name, email: account.email, password: account.password, password_confirm: account.confirm_password },
        {
          display_name: profile.display_name || account.full_name,
          birth_year: Number(profile.birth_year),
          gender: profile.gender || undefined,
          home_state: profile.home_state,
          home_city: profile.home_city,
          travel_states: profile.travel_states,
          competitive_level: profile.competitive_level as any,
          tennis_class: profile.tennis_class,
          preferred_modality: profile.preferred_modality,
          is_primary: true,
        },
      );
      toast.success('Dependente adicionado!');
      onAdded();
    } catch (err) {
      if (isEmailDuplicateError(err)) {
        setDuplicateEmailDetected(true);
      } else {
        toast.error(extractApiError(err));
      }
    }
    finally { setSaving(false); }
  }

  async function handleLinkExisting() {
    if (!account.email.trim()) return;
    setSaving(true);
    try {
      await linkExistingChild(account.email.trim());
      toast.success('Dependente vinculado com sucesso!');
      onAdded();
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card space-y-4 mb-3">
      <div>
        <h3 className="font-bold text-base">Novo dependente</h3>
        <p className="text-xs text-text-secondary mt-1">Preencha os dados de acesso e o perfil esportivo. Campos com * são obrigatórios.</p>
      </div>
      <hr className="border-border-subtle" />

      {/* Dados de acesso */}
      <div className="space-y-3">
        <h4 className="text-xs font-bold text-text-muted uppercase tracking-wide">Dados de acesso</h4>
        <div>
          <label className="text-xs text-text-secondary mb-1 block">Nome completo *</label>
          <input className="input-base" placeholder="Nome do dependente"
            value={account.full_name} onChange={(e) => setAccount({ ...account, full_name: e.target.value })} />
        </div>
        <div>
          <label className="text-xs text-text-secondary mb-1 block">E-mail *</label>
          <input className="input-base" type="email" placeholder="email@exemplo.com"
            value={account.email}
            onChange={(e) => { setAccount({ ...account, email: e.target.value }); setDuplicateEmailDetected(false); }} />
        </div>

        {duplicateEmailDetected && (
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 space-y-2">
            <div className="flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
              <div>
                <p className="text-sm font-semibold text-amber-400">Este e-mail já possui cadastro no Tenfy.</p>
                <p className="text-xs text-text-secondary mt-0.5">Deseja vincular esta conta existente como dependente do seu perfil?</p>
              </div>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                className="btn-primary flex-1 !text-xs !py-1.5"
                onClick={handleLinkExisting}
                disabled={saving}
              >
                {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin mx-auto" /> : 'Sim, vincular como dependente'}
              </button>
              <button
                type="button"
                className="btn-secondary !text-xs !py-1.5"
                onClick={() => setDuplicateEmailDetected(false)}
              >
                Cancelar
              </button>
            </div>
          </div>
        )}

        <div>
          <label className="text-xs text-text-secondary mb-1 block">Senha inicial *</label>
          <div className="relative">
            <input className="input-base pr-10" type={showPwd ? 'text' : 'password'} placeholder="Mínimo 8 caracteres"
              value={account.password} onChange={(e) => setAccount({ ...account, password: e.target.value })} />
            <button type="button" className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
              onClick={() => setShowPwd((v) => !v)}>
              {showPwd ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
        </div>
        <div>
          <label className="text-xs text-text-secondary mb-1 block">Confirmar senha *</label>
          <div className="relative">
            <input className="input-base pr-10" type={showConfirm ? 'text' : 'password'} placeholder="Repita a senha"
              value={account.confirm_password} onChange={(e) => setAccount({ ...account, confirm_password: e.target.value })} />
            <button type="button" className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
              onClick={() => setShowConfirm((v) => !v)}>
              {showConfirm ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
        </div>
      </div>

      <hr className="border-border-subtle" />

      {/* Perfil esportivo */}
      <div className="space-y-3">
        <h4 className="text-xs font-bold text-text-muted uppercase tracking-wide">Perfil esportivo</h4>
        <div>
          <label className="text-xs text-text-secondary mb-1 block">Nome do atleta</label>
          <input className="input-base" placeholder="Deixe em branco para usar o nome completo"
            value={profile.display_name} onChange={(e) => setProfile({ ...profile, display_name: e.target.value })} />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-xs text-text-secondary mb-1 block">Ano de nascimento *</label>
            <input className="input-base" type="number" min={1900} max={new Date().getFullYear()} placeholder="Ex: 2010"
              value={profile.birth_year} onChange={(e) => setProfile({ ...profile, birth_year: e.target.value })} />
          </div>
          <div>
            <label className="text-xs text-text-secondary mb-1 block">Gênero *</label>
            <select className="input-base" value={profile.gender}
              onChange={(e) => setProfile({ ...profile, gender: e.target.value as '' | 'M' | 'F' })}>
              <option value="">Selecione...</option>
              <option value="M">Masculino</option>
              <option value="F">Feminino</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-2">
          <div>
            <label className="text-xs text-text-secondary mb-1 block">Estado (UF) *</label>
            <select className="input-base" value={profile.home_state}
              onChange={(e) => setProfile({ ...profile, home_state: e.target.value, home_city: '' })}>
              {UF_OPTIONS.map((uf) => <option key={uf} value={uf}>{uf}</option>)}
            </select>
          </div>
          <div className="col-span-2">
            <label className="text-xs text-text-secondary mb-1 block">Cidade</label>
            {cities.length > 0 ? (
              <select className="input-base" value={profile.home_city}
                onChange={(e) => setProfile({ ...profile, home_city: e.target.value })}>
                <option value="">{loadingCities ? 'Carregando...' : 'Selecione a cidade'}</option>
                {cities.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            ) : (
              <input className="input-base" placeholder={loadingCities ? 'Carregando...' : 'Cidade'} value={profile.home_city}
                onChange={(e) => setProfile({ ...profile, home_city: e.target.value })} />
            )}
          </div>
        </div>

        <StateMultiSelect
          values={profile.travel_states}
          onChange={(vals) => setProfile({ ...profile, travel_states: vals })}
        />

        <div>
          <label className="text-xs text-text-secondary mb-1 block">Nível competitivo *</label>
          <select className="input-base" value={profile.competitive_level}
            onChange={(e) => setProfile({ ...profile, competitive_level: e.target.value })}>
            {Object.entries(LEVEL_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-text-secondary mb-1 block">Modalidade *</label>
          <select className="input-base" value={profile.preferred_modality}
            onChange={(e) => setProfile({ ...profile, preferred_modality: e.target.value })}>
            {MODALITY_OPTIONS.filter((o) => o.value).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-text-secondary mb-1 block">Classe (FPT/CBT)</label>
          <select className="input-base" value={profile.tennis_class}
            onChange={(e) => setProfile({ ...profile, tennis_class: e.target.value })}>
            <option value="">Sem classe definida</option>
            {Object.entries(TENNIS_CLASS_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
      </div>

      <div className="flex flex-col gap-2 pt-1">
        <button className="btn-primary w-full flex items-center justify-center gap-2" onClick={handleSubmit} disabled={saving}>
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
          Adicionar dependente
        </button>
        <button className="btn-secondary w-full" onClick={onCancel}>Cancelar</button>
      </div>
    </div>
  );
};
