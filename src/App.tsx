import { useEffect, useRef, useState } from 'react';
import { BookmarkSimple, CheckCircle, EnvelopeSimple, Gear, Keyboard, MagnifyingGlass, Plus, Stack, Star, SquaresFour, Trash, Users } from '@phosphor-icons/react';
import { api } from './api';
import { EMPTY_FILTERS, hasFilters, type DisplaySettings, type Filters, type Issue, type Project, type SavedView, type Status, type User } from './types';
import { Dialog, ErrorMessage, message } from './ui';
import { ProjectDialog, TicketDialog } from './forms';
import { IssueDetail } from './IssueDetail';
import { IssueBoard, IssueList, Toolbar } from './IssueViews';
import { ProjectGrid } from './ProjectViews';
import { SettingsView, type SettingsTab } from './SettingsView';
import { CommandPalette, ViewDialog, type Command } from './WorkspaceNavigation';
import { useWorkspace } from './useWorkspace';
import { useSettings } from './useSettings';
import { AccountDialog } from './AuthGate';
import { InvitationsDialog, ProjectMembersDialog } from './Sharing';
import { WorkspaceMenu, type WorkspaceControls } from './Workspaces';
import { WorkspaceMembersDialog } from './WorkspaceMembers';

type Modal = { kind: 'project'; project?: Project } | { kind: 'ticket'; status?: Status } | { kind: 'detail'; id: number } | { kind: 'view'; view?: SavedView } | { kind: 'deleteView'; view: SavedView } | { kind: 'members'; project: Project } | { kind: 'workspaceMembers' } | { kind: 'account' } | { kind: 'invitations' } | { kind: 'commands' } | { kind: 'help' } | null;
function linkedIssue(): Modal { const id = Number(new URLSearchParams(location.search).get('issue')); return Number.isSafeInteger(id) && id > 0 ? { kind: 'detail', id } : null; }

export default function App({ user, onSessionEnd, onUserUpdated, workspaceControls }: { user: User; onSessionEnd: (notice?: string) => void; onUserUpdated: (user: User) => void; workspaceControls: WorkspaceControls }) {
  const { workspace } = workspaceControls;
  const canCreateProject = workspace.role !== 'guest';
  const preferences = useSettings();
  const { settings, ready, save } = preferences;
  const { filters, display } = settings;
  const { projects, issues, labels, templates, views, error, loading, refresh, addLabel } = useWorkspace(filters, display, ready);
  const [section, setSection] = useState<'issues'|'projects'|'settings'>('issues');
  const [settingsTab, setSettingsTab] = useState<SettingsTab>('preferences');
  const [modal, setModal] = useState<Modal>(linkedIssue);
  const [pageMode, setPageMode] = useState(new URLSearchParams(location.search).get('mode') === 'page');
  const [selectedViewId, setSelectedViewId] = useState<number | null>(null);
  const [mutationError, setMutationError] = useState('');
  const [notice, setNotice] = useState('');
  const [pendingIds, setPendingIds] = useState(new Set<number>());
  const [deletingView, setDeletingView] = useState(false);
  const [invitationCount, setInvitationCount] = useState(0);
  const moving = useRef(new Set<number>());
  const initialized = useRef(false);
  const leaveSettings = useRef<(() => boolean) | null>(null);
  const registerNavigationGuard = useRef((guard: (() => boolean) | null) => { leaveSettings.current = guard; }).current;
  const searchRef = useRef<HTMLInputElement>(null);
  const activeProject = projects.find(project => String(project.id) === filters.projectId);
  const activeView = views.find(view => view.id === selectedViewId);
  const filtered = hasFilters(filters);
  const total = projects.reduce((sum, project) => sum + project.issueCount, 0);
  const title = section === 'settings' ? 'Paramètres' : section === 'projects' ? 'Projets' : activeView?.name || (filters.favoritesOnly ? 'Favoris' : activeProject?.name || 'Tous les tickets');
  const persist = (patch: Parameters<typeof save>[0]) => { void save(patch).catch(() => undefined); };
  const setFilters = (next: Filters) => persist({ filters: next });
  const setDisplay = (next: DisplaySettings) => persist({ display: next });
  function updateUrl(id?: number, full = pageMode) {
    const url = new URL(location.href);
    if (id) { url.searchParams.set('issue', String(id)); if (full) url.searchParams.set('mode', 'page'); else url.searchParams.delete('mode'); }
    else { url.searchParams.delete('issue'); url.searchParams.delete('mode'); }
    history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`);
  }
  const close = () => { setModal(null); updateUrl(); };
  function openIssue(id: number) { if (!moving.current.has(id)) { setModal({ kind: 'detail', id }); updateUrl(id); } }
  function navigate(next: typeof section) {
    if (next !== section && leaveSettings.current && !leaveSettings.current()) return false;
    setSection(next); return true;
  }
  function openTickets(id?: number, favoritesOnly = false) {
    if (!navigate('issues')) return; setSelectedViewId(null);
    setFilters({ ...EMPTY_FILTERS, projectId: id ? String(id) : '', favoritesOnly });
  }
  function openView(view: SavedView) { if (!navigate('issues')) return; setSelectedViewId(view.id); persist({ filters: view.filters, display: view.display }); }
  const newTicket = (status?: Status) => { if (!loading && (projects.length || canCreateProject)) setModal(projects.length ? { kind: 'ticket', status } : { kind: 'project' }); };
  const syncWorkspace = async () => { await preferences.reload(); await refresh(); };
  const saved = (text: string) => { setNotice(text); void refresh(); };
  const refreshInvitations = async () => { const [projects, spaces] = await Promise.all([api.invitations(), api.workspaceInbox()]); setInvitationCount(projects.length + spaces.length); };
  function canLeave() { return !preferences.saving && (!leaveSettings.current || leaveSettings.current()); }
  async function logout() { try { await api.logout(); onSessionEnd('Vous êtes déconnecté.'); } catch (error) { setMutationError(message(error)); } }
  useEffect(() => {
    const update = () => { void refreshInvitations().catch(() => undefined); };
    update();
    window.addEventListener('focus', update);
    return () => window.removeEventListener('focus', update);
  }, []);
  useEffect(() => {
    if (!ready || initialized.current) return;
    initialized.current = true;
    if (settings.homeView === 'projects' && !linkedIssue()) setSection('projects');
    if (settings.homeView === 'list' || settings.homeView === 'board') void save({ display: { ...settings.display, view: settings.homeView } }).catch(() => undefined);
  }, [ready, settings, save]);
  useEffect(() => { if (!notice) return; const timeout = setTimeout(() => setNotice(''), 4500); return () => clearTimeout(timeout); }, [notice]);
  useEffect(() => {
    const handle = (event: KeyboardEvent) => {
      const target = event.target;
      if (modal || document.querySelector('dialog[open], [role="menu"]')) return;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setModal({ kind: 'commands' }); return; }
      if (event.ctrlKey || event.metaKey || event.altKey || (target instanceof HTMLElement && (target.closest('input, textarea, select') || target.isContentEditable))) return;
      if (event.key.toLowerCase() === 'c' && !loading && (projects.length || canCreateProject)) { event.preventDefault(); setModal(projects.length ? { kind: 'ticket' } : { kind: 'project' }); }
      if (event.key === '/') { event.preventDefault(); if (!navigate('issues')) return; requestAnimationFrame(() => searchRef.current?.focus()); }
      if (event.key === '?') { event.preventDefault(); setModal({ kind: 'help' }); }
    };
    window.addEventListener('keydown', handle);
    return () => window.removeEventListener('keydown', handle);
  }, [modal, projects.length, section, loading]);
  async function mutateIssue(id: number, data: { status?: Status; isFavorite?: boolean }) {
    if (moving.current.has(id)) return;
    moving.current.add(id); setPendingIds(new Set(moving.current)); setMutationError('');
    try { await api.updateIssue(id, data); await refresh(); setNotice(data.status ? 'Statut du ticket enregistré' : data.isFavorite ? 'Ticket ajouté aux favoris' : 'Ticket retiré des favoris'); }
    catch (error) { setMutationError(message(error)); }
    finally { moving.current.delete(id); setPendingIds(new Set(moving.current)); }
  }
  async function deleteView(view: SavedView) {
    if (deletingView) return;
    setDeletingView(true); setMutationError('');
    try { await api.deleteView(view.id); if (selectedViewId === view.id) setSelectedViewId(null); close(); saved('Vue supprimée'); }
    catch (error) { setMutationError(message(error)); }
    finally { setDeletingView(false); }
  }
  const commands: Command[] = [
    { id: 'new-ticket', label: 'Créer un ticket', detail: 'C', run: () => newTicket() },
    ...(canCreateProject ? [{ id: 'new-project', label: 'Créer un projet', run: () => setModal({ kind: 'project' }) }] : []),
    { id: 'issues', label: 'Afficher tous les tickets', run: () => openTickets() },
    { id: 'favorites', label: 'Afficher les favoris', run: () => openTickets(undefined, true) },
    { id: 'projects', label: 'Afficher les projets', run: () => { navigate('projects'); } },
    { id: 'settings', label: 'Ouvrir les paramètres', run: () => { navigate('settings'); } },
    ...views.map(view => ({ id: `view-${view.id}`, label: `Ouvrir la vue ${view.name}`, run: () => openView(view) })),
  ];
  if (!ready) return <main className="form-body"><h1>Circular</h1><p role="status">Chargement des préférences…</p><ErrorMessage>{preferences.error}</ErrorMessage>{preferences.error && <button className="button" onClick={() => void preferences.reload()}>Réessayer</button>}</main>;
  return <div className="app-shell"><a className="skip-link" href="#workspace">Aller aux tickets et projets</a>
    <aside className="sidebar"><WorkspaceMenu controls={workspaceControls} user={user} canLeave={canLeave} onSettings={() => { setSettingsTab('workspace'); setSection('settings'); }} onMembers={() => setModal({ kind: 'workspaceMembers' })} onProfile={() => { setSettingsTab('profile'); setSection('settings'); }} onLogout={() => void logout()} />
      <div className="workspace-label">{workspace.role === 'guest' ? 'Accès invité' : 'Espace de travail'}</div>
      <nav aria-label="Navigation principale">
        <button className="nav-item" aria-label="Commandes" data-short-label="Commandes" onClick={() => setModal({ kind: 'commands' })}><MagnifyingGlass size={17} />Commandes<span className="nav-count">Ctrl K</span></button>
        <button className={`nav-item ${section === 'issues' && !filters.projectId && !filters.favoritesOnly && !activeView ? 'active' : ''}`} aria-label="Tous les tickets" data-short-label="Tickets" onClick={() => openTickets()}><Stack size={17} />Tous les tickets<span className="nav-count">{total}</span></button>
        <button className={`nav-item ${section === 'issues' && filters.favoritesOnly ? 'active' : ''}`} aria-label="Favoris" data-short-label="Favoris" onClick={() => openTickets(undefined, true)}><Star size={17} />Favoris</button>
        <button className={`nav-item ${section === 'projects' ? 'active' : ''}`} aria-label="Projets" data-short-label="Projets" onClick={() => { navigate('projects'); }}><SquaresFour size={17} />Projets<span className="nav-count">{projects.length}</span></button>
        <button className={`nav-item ${section === 'settings' ? 'active' : ''}`} aria-label="Paramètres" data-short-label="Réglages" onClick={() => { navigate('settings'); }}><Gear size={17} />Paramètres</button>
      </nav>
      <div className="sidebar-section"><span>VUES ENREGISTRÉES</span><button className="icon-button" aria-label="Enregistrer une vue" title="Enregistrer les filtres et l’affichage" onClick={() => setModal({ kind: 'view' })}><Plus size={15} /></button></div>
      <div className="saved-views">{views.map(view => <div className="saved-view-row" key={view.id}><button className={`nav-item ${section === 'issues' && selectedViewId === view.id ? 'active' : ''}`} onClick={() => openView(view)}><BookmarkSimple size={15} /><span className="truncate">{view.name}</span></button><button className="icon-button" aria-label={`Supprimer la vue ${view.name}`} onClick={() => setModal({ kind: 'deleteView', view })}><Trash size={14} /></button></div>)}</div>
      <div className="sidebar-section"><span>PROJETS</span><button className="icon-button" aria-label="Nouveau projet" title="Nouveau projet" disabled={!canCreateProject} onClick={() => setModal({ kind: 'project' })}><Plus size={15} /></button></div>
      <div className="project-shortcuts">{projects.map(project => <button key={project.id} className={`nav-item ${section === 'issues' && filters.projectId === String(project.id) ? 'active' : ''}`} onClick={() => openTickets(project.id)}><span className="project-dot" style={{ background: project.color }} /><span className="truncate">{project.name}</span><span className="nav-count">{project.issueCount}</span></button>)}</div>
      <div className="sidebar-bottom"><span className={`connection-dot ${error ? 'offline' : ''}`} />{error ? 'Connexion à vérifier' : workspace.role === 'guest' ? 'Accès invité' : 'Espace de travail'}<button className="icon-button help-button" aria-label="Raccourcis clavier" title="Raccourcis clavier (?)" onClick={() => setModal({ kind: 'help' })}><Keyboard size={17} /></button><span className="sidebar-private">Projets de cet espace</span></div>
    </aside>
    <main className="main-content"><header className="topbar"><span className="breadcrumb">{workspace.name}<span>/</span><strong>{title}</strong></span><span className="settings-save-state" role="status">{preferences.saving ? 'Enregistrement des réglages…' : preferences.error ? 'Réglages non enregistrés' : 'Réglages enregistrés'}</span><div className="account-controls"><button className="icon-button" aria-label="Invitations" title="Invitations" onClick={() => setModal({ kind: 'invitations' })}><EnvelopeSimple size={19} />{invitationCount > 0 && <span className="account-count">{invitationCount}</span>}</button><button className="account-button" aria-label="Mon compte" title={user.displayName || user.username} onClick={() => { if (!leaveSettings.current || leaveSettings.current()) setModal({ kind: 'account' }); }}><span className="account-avatar" aria-hidden="true">{(user.displayName || user.username)[0]?.toUpperCase()}</span><span>{user.displayName || user.username}</span></button><button className="icon-button help-account-button" aria-label="Raccourcis clavier" onClick={() => setModal({ kind: 'help' })}><Keyboard size={16} /></button></div></header>
      <section className="page-heading"><div className="heading-content"><div className="heading-title"><h1 id="workspace" tabIndex={-1}>{title}</h1>{activeProject && section === 'issues' && <span className="project-key heading-key">{activeProject.key}</span>}</div>{section === 'projects' ? <p>{projects.length} projet{projects.length !== 1 ? 's' : ''} dans cet espace</p> : section === 'settings' ? <p>Votre espace, votre façon de travailler.</p> : activeProject?.description && <p>{activeProject.description}</p>}</div>{section !== 'settings' && <button className="button primary" disabled={(loading && section === 'issues') || (!canCreateProject && (section === 'projects' || !projects.length))} aria-label={section === 'projects' ? 'Nouveau projet' : 'Nouveau ticket'} onClick={() => section === 'projects' ? setModal({ kind: 'project' }) : newTicket()}><Plus size={16} /><span>{section === 'projects' ? 'Nouveau projet' : 'Nouveau ticket'}</span>{section === 'issues' && <kbd aria-hidden="true">C</kbd>}</button>}</section>
      {activeProject && section === 'issues' && <div className="project-context-actions"><button className="button subtle" onClick={() => setModal({ kind: 'members', project: activeProject })}><Users size={16} />Membres du projet</button></div>}
      {preferences.error && <div className="settings-error"><ErrorMessage>{preferences.error}</ErrorMessage><button className="button" onClick={() => void preferences.retry().catch(() => undefined)}>Réessayer l’enregistrement des réglages</button></div>}
      {section === 'issues' && <><Toolbar filters={filters} setFilters={setFilters} projects={projects} labels={labels} display={display} onDisplayChange={setDisplay} view={display.view} setView={view => setDisplay({ ...display, view })} searchRef={searchRef} /><div className="view-actions"><span className="view-name">{activeView ? `Vue : ${activeView.name}` : 'Vue personnelle'}</span><button className="button subtle" onClick={() => setModal({ kind: 'view' })}>Enregistrer cette vue</button>{activeView && <button className="button subtle" onClick={() => setModal({ kind: 'view', view: activeView })}>Mettre à jour la vue</button>}</div></>}
      <ErrorMessage>{error || mutationError}</ErrorMessage>{error && <button className="button retry-button" onClick={() => void refresh()}>Réessayer</button>}
      {section === 'issues' && <div className="result-summary"><span>{loading ? 'Chargement…' : `${issues.length} ticket${issues.length !== 1 ? 's' : ''}${filtered ? ' dans cette vue' : ''}`}</span><span>{display.view === 'board' ? 'Glissez les tickets pour changer leur statut' : 'Affichage personnalisable'}</span></div>}
      {section === 'settings' ? <SettingsView settings={settings} labels={labels} templates={templates} projects={projects} onSaveSettings={save} onChanged={syncWorkspace} onNavigationGuardChange={registerNavigationGuard} initialTab={settingsTab} onTabChange={setSettingsTab} workspace={workspace} user={user} onWorkspaceUpdated={workspaceControls.updateWorkspace} onUserUpdated={onUserUpdated} /> : loading ? <div className="loading-state" role="status">Chargement de votre espace…</div> : section === 'projects' ? <ProjectGrid projects={projects} onOpen={openTickets} onEdit={project => setModal({ kind: 'project', project })} onMembers={project => setModal({ kind: 'members', project })} /> : display.view === 'board' && (issues.length > 0 || projects.length > 0) ? <IssueBoard issues={issues} projects={projects} pendingIds={pendingIds} display={display} onDisplayChange={setDisplay} onFavorite={issue => void mutateIssue(issue.id, { isFavorite: !issue.isFavorite })} onOpen={openIssue} onMove={(id, status) => void mutateIssue(id, { status })} onCreate={newTicket} /> : <IssueList issues={issues} projects={projects} pendingIds={pendingIds} display={display} onDisplayChange={setDisplay} onFavorite={issue => void mutateIssue(issue.id, { isFavorite: !issue.isFavorite })} onOpen={openIssue} />}
      {!loading && !error && section !== 'settings' && (section === 'projects' ? !projects.length : !issues.length && (display.view === 'list' || !projects.length)) && <div className="empty-state"><span className="empty-icon"><Stack size={28} /></span><h2>{filtered && projects.length ? 'Aucun ticket ne correspond.' : projects.length ? 'Aucun ticket pour le moment.' : canCreateProject ? 'Créez votre premier projet.' : 'Aucun projet partagé.'}</h2><p>{filtered && projects.length ? 'Essayez une autre recherche ou élargissez vos filtres.' : projects.length ? 'Ajoutez un ticket à un projet pour commencer.' : canCreateProject ? 'Vous pourrez ensuite y organiser vos tickets.' : 'Les projets auxquels vous êtes invité apparaîtront ici.'}</p>{filtered && projects.length ? <button className="button" onClick={() => setFilters(EMPTY_FILTERS)}>Afficher tous les tickets</button> : <button className="button" disabled={!canCreateProject && (section === 'projects' || !projects.length)} onClick={() => projects.length && section === 'issues' ? newTicket() : setModal({ kind: 'project' })}><Plus size={16} />{projects.length && section === 'issues' ? 'Créer un ticket' : 'Créer un projet'}</button>}</div>}
    </main>
    {!!notice && <div className="toast" role="status"><CheckCircle size={15} />{notice}</div>}
    {modal?.kind === 'account' && <AccountDialog user={user} onClose={close} onSessionEnd={onSessionEnd} />}
    {modal?.kind === 'invitations' && <InvitationsDialog onClose={close} onChanged={async id => { await workspaceControls.refreshWorkspaces(id); if (!id || id === workspace.id) { await refresh(); await refreshInvitations(); } }} />}
    {modal?.kind === 'workspaceMembers' && <WorkspaceMembersDialog workspace={workspace} user={user} onClose={close} onLeft={async () => { await workspaceControls.refreshWorkspaces(); close(); }} />}
    {modal?.kind === 'members' && <ProjectMembersDialog project={modal.project} onClose={close} />}
    {modal?.kind === 'project' && <ProjectDialog project={modal.project} onClose={close} onSaved={() => saved(modal.project ? 'Projet enregistré' : 'Projet créé')} onDeleted={() => { void syncWorkspace(); setNotice('Projet supprimé'); }} />}
    {modal?.kind === 'ticket' && <TicketDialog projects={projects} labels={labels} templates={templates} projectId={activeProject?.id} status={modal.status} onClose={close} onSaved={() => { navigate('issues'); setFilters({ ...EMPTY_FILTERS, projectId: filters.projectId }); saved('Ticket créé'); }} onLabelCreated={addLabel} />}
    {modal?.kind === 'detail' && <IssueDetail key={modal.id} id={modal.id} projects={projects} labels={labels} commentSubmit={settings.commentSubmit} pageMode={pageMode} onPageModeChange={full => { setPageMode(full); updateUrl(modal.id, full); }} onDuplicate={(issue: Issue) => { saved('Ticket dupliqué'); openIssue(issue.id); }} onFavoriteChanged={() => void refresh()} onClose={close} onSaved={() => saved('Ticket enregistré')} onDeleted={() => saved('Ticket supprimé')} onLabelCreated={addLabel} />}
    {modal?.kind === 'view' && <ViewDialog view={modal.view} filters={filters} display={display} onClose={close} onSaved={view => { setSelectedViewId(view.id); saved('Vue enregistrée'); }} />}
    {modal?.kind === 'deleteView' && <Dialog title="Supprimer la vue" onClose={close} pending={deletingView}><div className="form-body"><p>Supprimer « {modal.view.name} » ? Les tickets seront conservés.</p><ErrorMessage>{mutationError}</ErrorMessage><div className="view-delete-actions"><button className="button" disabled={deletingView} onClick={close}>Annuler</button><button className="button danger" disabled={deletingView} onClick={() => void deleteView(modal.view)}>{deletingView ? 'Suppression…' : 'Supprimer la vue'}</button></div></div></Dialog>}
    {modal?.kind === 'commands' && <CommandPalette commands={commands} onOpenIssue={openIssue} onClose={close} />}
    {modal?.kind === 'help' && <Dialog title="Raccourcis clavier" onClose={close}><div className="form-body"><ul className="shortcut-list"><li><span>Créer un ticket</span><kbd>C</kbd></li><li><span>Rechercher</span><kbd>/</kbd></li><li><span>Ouvrir les commandes</span><kbd>Ctrl / ⌘ + K</kbd></li><li><span>Enregistrer un formulaire</span><kbd>Ctrl / ⌘ + Entrée</kbd></li><li><span>Fermer un panneau</span><kbd>Échap</kbd></li><li><span>Afficher les raccourcis</span><kbd>?</kbd></li></ul><p className="help-note">Les raccourcis de navigation sont désactivés pendant la saisie. Un avertissement protège vos modifications non enregistrées à la fermeture d’un panneau.</p></div></Dialog>}
  </div>;
}
