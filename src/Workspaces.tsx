import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ArrowLeft, ArrowRight, Buildings, CaretDown, Check, Gear, Link, Plus, SignOut, UserCircle, Users } from '@phosphor-icons/react';
import { api, setWorkspaceId } from './api';
import type { User, Workspace } from './types';
import { ErrorMessage, message } from './ui';
import { IntegrationsPanel } from './IntegrationsPanel';
import { WorkspaceInviteForm } from './WorkspaceMembers';
import { InvitationsDialog } from './Sharing';
import './workspace-onboarding.css';

export type WorkspaceControls = {
  workspace: Workspace;
  workspaces: Workspace[];
  selectWorkspace: (id: number) => void;
  createWorkspace: () => void;
  refreshWorkspaces: (selectId?: number) => Promise<void>;
  updateWorkspace: (workspace: Workspace) => void;
};

function workspaceUrl(workspace: Workspace, preserveIssue = false) {
  const url = new URL(location.href);
  url.searchParams.set('workspace', workspace.slug);
  if (!preserveIssue) url.searchParams.delete('setup');
  if (!preserveIssue) { url.searchParams.delete('issue'); url.searchParams.delete('mode'); }
  history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`);
}
function inviteToken() { return new URLSearchParams(location.hash.slice(1)).get('workspace-invite'); }

export function WorkspaceGate({ user, onUserUpdated, onSessionEnd, children }: { user: User; onUserUpdated: (user: User) => void; onSessionEnd: (notice?: string) => void; children: (controls: WorkspaceControls) => ReactNode }) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selectedId, setSelectedId] = useState<number>();
  const selected = useRef<number | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [creating, setCreating] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const [inbox, setInbox] = useState(false);
  const [token, setToken] = useState(inviteToken);
  const sequence = useRef(0);
  const workspace = workspaces.find(item => item.id === selectedId);

  function select(next: Workspace, preserveIssue = false) {
    setWorkspaceId(next.id); selected.current = next.id; setSelectedId(next.id);
    setCreating(false); setUnavailable(false); workspaceUrl(next, preserveIssue);
  }
  async function load(initial = false, preferredId?: number) {
    const version = ++sequence.current;
    const next = await api.workspaces();
    if (version !== sequence.current) return;
    setWorkspaces(next);
    const slug = new URLSearchParams(location.search).get('workspace');
    const active = preferredId ? next.find(item => item.id === preferredId) : initial && slug ? next.find(item => item.slug === slug) : next.find(item => item.id === selected.current) || next[0];
    if (initial && slug && !active) { setWorkspaceId(); setUnavailable(true); return; }
    if (active) select(active, initial || !preferredId);
    else { setWorkspaceId(); selected.current = undefined; setSelectedId(undefined); }
  }
  useEffect(() => {
    let active = true;
    load(true).catch(error => { if (active) setError(message(error)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; sequence.current++; };
  }, []);
  useEffect(() => {
    const changed = () => setToken(inviteToken());
    window.addEventListener('hashchange', changed);
    return () => window.removeEventListener('hashchange', changed);
  }, []);
  async function retry() { setLoading(true); setError(''); try { await load(true); } catch (error) { setError(message(error)); } finally { setLoading(false); } }
  function updated(next: Workspace) { setWorkspaces(current => current.map(item => item.id === next.id ? next : item)); if (selected.current === next.id) workspaceUrl(next, true); }
  async function finish(next: Workspace) { updated(next); select(next); }
  async function created(next: Workspace) { setWorkspaces(current => [...current.filter(item => item.id !== next.id), next]); select(next); }
  function clearInvite() { history.replaceState(null, '', `${location.pathname}${location.search}`); setToken(null); }

  if (loading || error) return <main className="auth-shell"><div className="auth-card"><div className="auth-brand"><span className="brand-mark" />Circular</div><h1>Votre espace de travail</h1>{loading ? <p role="status">Chargement des espaces…</p> : <><ErrorMessage>{error}</ErrorMessage><button className="button primary" onClick={() => void retry()}>Réessayer</button></>}</div></main>;
  if (token) return <JoinWorkspace token={token} user={user} onCancel={clearInvite} onJoined={async next => { clearInvite(); await load(false, next.id); }} />;
  if (unavailable) return <main className="auth-shell"><div className="auth-card"><h1>Espace inaccessible</h1><p className="auth-intro">Vous ne disposez pas d’un accès à cet espace, ou son identifiant a changé.</p><div className="workspace-choice-list">{workspaces.map(item => <button className="button" key={item.id} onClick={() => select(item)}>Ouvrir {item.name}</button>)}</div><button className="button primary" onClick={() => { setUnavailable(false); setCreating(true); }}>Créer un espace</button></div></main>;
  if (creating || !workspace) return <><CreateWorkspace user={user} onCreated={created} onCancel={workspace ? () => setCreating(false) : undefined} onInbox={() => setInbox(true)} onSessionEnd={onSessionEnd} />{inbox && <InvitationsDialog onClose={() => setInbox(false)} onChanged={async id => { await load(false, id); setInbox(false); }} />}</>;
  if (!workspace.onboardingCompleted && workspace.role === 'owner') return <WorkspaceOnboarding key={workspace.id} workspace={workspace} user={user} onUserUpdated={onUserUpdated} onComplete={finish} onSessionEnd={onSessionEnd} />;
  return children({ workspace, workspaces, selectWorkspace: id => { const next = workspaces.find(item => item.id === id); if (next) select(next); }, createWorkspace: () => setCreating(true), refreshWorkspaces: id => load(false, id), updateWorkspace: updated });
}

function OnboardingShell({ user, title, intro, step, children, onSessionEnd }: { user: User; title: string; intro: string; step: number; children: ReactNode; onSessionEnd?: (notice?: string) => void }) {
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  async function logout() { setPending(true); setError(''); try { await api.logout(); onSessionEnd?.('Vous êtes déconnecté.'); } catch (error) { setError(message(error)); } finally { setPending(false); } }
  return <main className="onboarding-shell"><header className="onboarding-top"><div className="onboarding-brand"><span className="brand-mark" aria-hidden="true" />Circular</div><div className="onboarding-user"><span>{user.email}</span>{onSessionEnd && <button className="button subtle" disabled={pending} onClick={() => void logout()}>Se déconnecter</button>}</div></header><section className="onboarding-content"><div className="onboarding-symbol" aria-hidden="true">{step === 0 ? <Buildings size={25} /> : step === 1 ? <UserCircle size={25} /> : step === 2 ? <Users size={25} /> : <Link size={25} />}</div><h1 tabIndex={-1}>{title}</h1><p className="onboarding-intro">{intro}</p><ErrorMessage>{error}</ErrorMessage>{children}</section><ol className="onboarding-progress" aria-label="Étapes de configuration">{['Espace', 'Profil', 'Équipe', 'Outils'].map((label, index) => <li className={index < step ? 'completed' : ''} aria-current={index === step ? 'step' : undefined} key={label}><span>{index < step ? <Check size={12} /> : index + 1}</span>{label}</li>)}</ol></main>;
}

function slugify(value: string) { return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 50); }

function CreateWorkspace({ user, onCreated, onCancel, onInbox, onSessionEnd }: { user: User; onCreated: (workspace: Workspace) => Promise<void>; onCancel?: () => void; onInbox: () => void; onSessionEnd: (notice?: string) => void }) {
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [slugEdited, setSlugEdited] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  async function create() { if (pending) return; setPending(true); setError(''); try { const result = await api.createWorkspace({ name: name.trim(), slug }); await onCreated(result.workspace); } catch (error) { setError(message(error)); } finally { setPending(false); } }
  return <OnboardingShell user={user} step={0} title="Créer votre espace" intro="Un espace réunit vos projets, vos tickets et les personnes avec qui vous travaillez." onSessionEnd={onSessionEnd}><form aria-busy={pending} onSubmit={event => { event.preventDefault(); void create(); }}><fieldset className="onboarding-fields" disabled={pending}><ErrorMessage>{error}</ErrorMessage><label>Nom de l’espace<input required minLength={2} maxLength={100} value={name} autoFocus onChange={event => { setName(event.target.value); if (!slugEdited) setSlug(slugify(event.target.value)); }} placeholder="Ex. Équipe Horizon" /></label><label>Identifiant de l’espace<input aria-label="Identifiant de l’espace" required minLength={3} maxLength={50} pattern="[a-z0-9]+(?:-[a-z0-9]+)*" value={slug} onChange={event => { setSlug(event.target.value.toLowerCase()); setSlugEdited(true); }} placeholder="equipe-horizon" /><span className="field-hint">Lettres minuscules, chiffres et tirets. Vous pourrez le modifier dans les paramètres.</span></label><div className="onboarding-slug"><Link size={16} aria-hidden="true" /><span>{location.host}/?workspace=<code>{slug || 'votre-espace'}</code></span></div><p className="field-hint">Votre premier projet et trois tickets de bienvenue seront créés avec cet espace.</p></fieldset><div className="onboarding-actions">{onCancel && <button type="button" className="button subtle" disabled={pending} onClick={onCancel}><ArrowLeft size={16} />Retour</button>}<button className="button primary" disabled={pending || !name.trim() || slug.length < 3} type="submit">{pending ? 'Création…' : 'Créer l’espace'}<ArrowRight size={16} /></button></div></form><div className="onboarding-account-links"><button className="button subtle" disabled={pending} onClick={onInbox}>Voir mes invitations</button></div></OnboardingShell>;
}

function WorkspaceOnboarding({ workspace, user, onUserUpdated, onComplete, onSessionEnd }: { workspace: Workspace; user: User; onUserUpdated: (user: User) => void; onComplete: (workspace: Workspace) => Promise<void>; onSessionEnd: (notice?: string) => void }) {
  const [inviteBusy, setInviteBusy] = useState(false);
  const [inviteDirty, setInviteDirty] = useState(false);
  const [step, setStep] = useState(() => new URLSearchParams(location.search).get('setup') === 'tools' && user.profileCompleted ? 3 : user.profileCompleted ? 2 : 1);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  function go(next: number) { setStep(next); const url = new URL(location.href); url.searchParams.set('setup', next === 3 ? 'tools' : next === 2 ? 'invite' : 'profile'); history.replaceState(null, '', `${url.pathname}${url.search}`); requestAnimationFrame(() => document.querySelector<HTMLElement>('.onboarding-content h1')?.focus()); }
  async function finish() { if (pending) return; setPending(true); setError(''); try { await onComplete(await api.finishOnboarding(workspace.id)); } catch (error) { setError(message(error)); } finally { setPending(false); } }
  const titles = ['', 'Votre profil', 'Invitez votre équipe', 'Vos outils, au même endroit'];
  const intros = ['', 'Choisissez le nom qui apparaîtra dans vos commentaires et auprès de votre équipe.', `Partagez « ${workspace.name} » avec les personnes qui participent à vos projets.`, 'Préparez les liens avec vos outils habituels. Cette étape est facultative.'];
  return <OnboardingShell user={user} step={step} title={titles[step]} intro={intros[step]} onSessionEnd={onSessionEnd}>
    {step === 1 && <ProfileForm user={user} onboarding onSaved={next => { onUserUpdated(next); go(2); }} />}
    {step === 2 && <><WorkspaceInviteForm workspace={workspace} onPendingChange={setInviteBusy} onDraftChange={setInviteDirty} /><div className="onboarding-actions"><button className="button subtle onboarding-back" disabled={inviteBusy} onClick={() => { if (!inviteDirty || window.confirm('Revenir sans envoyer les invitations saisies ?')) go(1); }}><ArrowLeft size={16} />Retour</button><button className="button subtle" disabled={inviteBusy} onClick={() => { if (!inviteDirty || window.confirm('Continuer sans envoyer les invitations saisies ?')) go(3); }}>Passer cette étape</button><button className="button primary" disabled={inviteBusy} onClick={() => { if (!inviteDirty || window.confirm('Continuer sans envoyer les invitations saisies ?')) go(3); }}>Continuer<ArrowRight size={16} /></button></div></>}
    {step === 3 && <><IntegrationsPanel /><ErrorMessage>{error}</ErrorMessage><div className="onboarding-actions"><button className="button subtle onboarding-back" disabled={pending} onClick={() => go(2)}><ArrowLeft size={16} />Retour</button><button className="button primary" disabled={pending} onClick={() => void finish()}>{pending ? 'Ouverture…' : 'Ouvrir mon espace'}<ArrowRight size={16} /></button></div></>}
  </OnboardingShell>;
}

export function ProfileForm({ user, onSaved, onboarding = false, onDirtyChange, onPendingChange }: { user: User; onSaved: (user: User) => void; onboarding?: boolean; onDirtyChange?: (dirty: boolean) => void; onPendingChange?: (pending: boolean) => void }) {
  const [displayName, setDisplayName] = useState(user.displayName || user.username);
  const [title, setTitle] = useState(user.title || '');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  useEffect(() => { onDirtyChange?.(displayName !== (user.displayName || user.username) || title !== (user.title || '')); }, [displayName, title, user, onDirtyChange]);
  useEffect(() => { onPendingChange?.(pending); }, [pending, onPendingChange]);
  async function save(skip = false) { if (pending) return; setPending(true); setError(''); try { const next = await api.updateProfile({ displayName: skip ? user.displayName || user.username : displayName.trim(), title: skip ? user.title || '' : title.trim() }); setDisplayName(next.displayName || next.username); setTitle(next.title || ''); onSaved(next); setSaved(true); } catch (error) { setError(message(error)); } finally { setPending(false); } }
  return <form className={onboarding ? '' : 'workspace-details-form'} aria-busy={pending} onSubmit={event => { event.preventDefault(); void save(); }}><fieldset className="onboarding-fields" disabled={pending}><ErrorMessage>{error}</ErrorMessage>{saved && !onboarding && <p className="settings-notice" role="status">Profil enregistré.</p>}<label>Nom affiché<input required maxLength={100} value={displayName} onChange={event => { setDisplayName(event.target.value); setSaved(false); }} autoComplete="name" autoFocus={onboarding} /></label><label>Titre ou rôle<input aria-label="Titre ou rôle" maxLength={100} value={title} onChange={event => { setTitle(event.target.value); setSaved(false); }} placeholder="Ex. Étudiant, responsable du projet…" /><span className="field-hint">Facultatif. Ce titre sera visible par les membres de vos espaces.</span></label></fieldset><div className="onboarding-actions">{onboarding && <button className="button subtle" type="button" disabled={pending} onClick={() => void save(true)}>Passer cette étape</button>}<button className="button primary" type="submit" disabled={pending || !displayName.trim()}>{pending ? 'Enregistrement…' : onboarding ? 'Enregistrer et continuer' : 'Enregistrer le profil'}{onboarding && <ArrowRight size={16} />}</button></div></form>;
}

export function WorkspaceSettings({ workspace, onSaved, onDirtyChange, onPendingChange }: { workspace: Workspace; onSaved: (workspace: Workspace) => void; onDirtyChange?: (dirty: boolean) => void; onPendingChange?: (pending: boolean) => void }) {
  const [name, setName] = useState(workspace.name);
  const [slug, setSlug] = useState(workspace.slug);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  useEffect(() => { onDirtyChange?.(name !== workspace.name || slug !== workspace.slug); }, [name, slug, workspace, onDirtyChange]);
  useEffect(() => { onPendingChange?.(pending); }, [pending, onPendingChange]);
  async function save() { if (pending) return; setPending(true); setError(''); try { const next = await api.updateWorkspace(workspace.id, { name: name.trim(), slug }); setName(next.name); setSlug(next.slug); onSaved(next); setSaved(true); } catch (error) { setError(message(error)); } finally { setPending(false); } }
  return <form className="workspace-details-form" onSubmit={event => { event.preventDefault(); void save(); }}><div className="settings-heading"><div><h2>Votre espace</h2><p>Le nom et l’identifiant de votre équipe dans Circular.</p></div></div><ErrorMessage>{error}</ErrorMessage>{saved && <p className="settings-notice" role="status">Espace enregistré.</p>}<fieldset className="onboarding-fields" disabled={pending || workspace.role !== 'owner'}><label>Nom de l’espace<input required minLength={2} maxLength={100} value={name} onChange={event => { setName(event.target.value); setSaved(false); }} /></label><label>Identifiant de l’espace<input aria-label="Identifiant de l’espace" required minLength={3} maxLength={50} pattern="[a-z0-9]+(?:-[a-z0-9]+)*" value={slug} onChange={event => { setSlug(event.target.value.toLowerCase()); setSaved(false); }} /></label></fieldset>{workspace.role === 'owner' ? <button className="button primary" disabled={pending || (name === workspace.name && slug === workspace.slug)} type="submit">{pending ? 'Enregistrement…' : 'Enregistrer l’espace'}</button> : <p className="workspace-settings-note">Seul le propriétaire peut modifier ces informations.</p>}</form>;
}

export function WorkspaceMenu({ controls, user, onSettings, onMembers, onProfile, onLogout, canLeave }: { controls: WorkspaceControls; user: User; onSettings: () => void; onMembers: () => void; onProfile: () => void; onLogout: () => void; canLeave: () => boolean }) {
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const container = useRef<HTMLDivElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  function close(focus = false) { setOpen(false); if (focus) trigger.current?.focus(); }
  function run(action: () => void) { if (!canLeave()) return; close(); action(); }
  useEffect(() => {
    if (!open) return;
    menu.current?.querySelector<HTMLButtonElement>('button')?.focus();
    const outside = (event: PointerEvent) => { if (!container.current?.contains(event.target as Node)) close(); };
    document.addEventListener('pointerdown', outside);
    return () => document.removeEventListener('pointerdown', outside);
  }, [open]);
  return <div className="workspace-switcher" ref={container} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setOpen(false); }}><button className="workspace-trigger" ref={trigger} aria-label="Menu de l’espace" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(value => !value)} onKeyDown={event => { if (event.key === 'ArrowDown') { event.preventDefault(); setOpen(true); } }}><span className="workspace-mark" aria-hidden="true">{controls.workspace.name.slice(0, 2).toUpperCase()}</span><span className="workspace-trigger-copy"><strong>{controls.workspace.name}</strong><small>Circular</small></span><CaretDown size={14} aria-hidden="true" /></button>{open && <div className="workspace-menu" ref={menu} role="menu" aria-label="Espace de travail" onKeyDown={event => { const items = [...(menu.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') || [])]; const index = items.indexOf(document.activeElement as HTMLButtonElement); if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(true); } else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) { event.preventDefault(); const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length; items[next]?.focus(); } }}><div className="workspace-menu-user"><strong>{user.displayName || user.username}</strong><small>{user.email}</small></div><button role="menuitem" onClick={() => run(onSettings)}><Gear size={16} />Paramètres de l’espace</button>{controls.workspace.role !== 'guest' && <button role="menuitem" onClick={() => run(onMembers)}><Users size={16} />Membres de l’espace</button>}<button role="menuitem" onClick={() => run(onProfile)}><UserCircle size={16} />Mon profil</button><div role="separator" /><span className="workspace-menu-label">CHANGER D’ESPACE</span>{controls.workspaces.map(item => <button role="menuitemradio" aria-checked={item.id === controls.workspace.id} aria-label={`Ouvrir l’espace ${item.name}`} key={item.id} onClick={() => run(() => controls.selectWorkspace(item.id))}><span>{item.name}</span>{item.id === controls.workspace.id && <Check size={15} />}</button>)}<button role="menuitem" onClick={() => run(controls.createWorkspace)}><Plus size={16} />Créer un espace</button><div role="separator" /><button role="menuitem" onClick={() => run(onLogout)}><SignOut size={16} />Se déconnecter</button></div>}</div>;
}

function JoinWorkspace({ token, user, onCancel, onJoined }: { token: string; user: User; onCancel: () => void; onJoined: (workspace: Workspace) => Promise<void> }) {
  const [preview, setPreview] = useState<{ workspaceName: string; workspaceSlug: string; expiresAt: string }>();
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  useEffect(() => { let active = true; api.previewWorkspaceLink(token).then(value => { if (active) setPreview(value); }).catch(error => { if (active) setError(message(error)); }); return () => { active = false; }; }, [token]);
  async function join() { setPending(true); setError(''); try { await onJoined(await api.acceptWorkspaceLink(token)); } catch (error) { setError(message(error)); } finally { setPending(false); } }
  return <OnboardingShell user={user} step={2} title={preview ? `Rejoindre ${preview.workspaceName}` : 'Invitation à un espace'} intro="En rejoignant cet espace, vous pourrez collaborer avec ses membres sur les projets partagés."><ErrorMessage>{error}</ErrorMessage>{!preview && !error && <p role="status">Vérification de l’invitation…</p>}<div className="onboarding-actions"><button className="button subtle" disabled={pending} onClick={onCancel}>Annuler</button>{preview && <button className="button primary" disabled={pending} onClick={() => void join()}>{pending ? 'Ajout…' : 'Rejoindre l’espace'}</button>}</div></OnboardingShell>;
}
