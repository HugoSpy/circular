import { useEffect, useState } from 'react';
import { ArrowsClockwise, Check, EnvelopeSimple, Users, X } from '@phosphor-icons/react';
import { api } from './api';
import type { IncomingWorkspaceInvitation, Invitation, Project, ProjectInvitation, ProjectMember } from './types';
import { Dialog, ErrorMessage, message } from './ui';

export function InvitationsDialog({ onClose, onChanged }: { onClose: () => void; onChanged: (workspaceId?: number) => Promise<void> }) {
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [workspaceInvitations, setWorkspaceInvitations] = useState<IncomingWorkspaceInvitation[]>([]);
  const [joinedId, setJoinedId] = useState<number>();
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  async function load() { setLoading(true); setError(''); try { const [projects, spaces] = await Promise.all([api.invitations(), api.workspaceInbox()]); setInvitations(projects); setWorkspaceInvitations(spaces); } catch (error) { setError(message(error)); } finally { setLoading(false); } }
  useEffect(() => { void load(); }, []);
  async function respond(invitation: Invitation, accept: boolean) {
    if (pending !== null) return;
    setPending(invitation.id); setError(''); setNotice('');
    try {
      if (accept) await api.acceptInvitation(invitation.id); else await api.declineInvitation(invitation.id);
      setInvitations(current => current.filter(item => item.id !== invitation.id));
      if (accept && invitation.workspaceId) setJoinedId(invitation.workspaceId);
      setNotice(accept ? `Vous avez rejoint « ${invitation.projectName} ». Retrouvez-le dans vos projets.` : 'Invitation refusée.');
    } catch (error) { setError(message(error)); }
    finally { setPending(null); }
  }
  async function respondWorkspace(invitation: IncomingWorkspaceInvitation, accept: boolean) {
    if (pending !== null) return;
    setPending(invitation.id); setError(''); setNotice('');
    try { if (accept) { const next = await api.acceptWorkspaceInvitation(invitation.id); setJoinedId(next.id); } else await api.declineWorkspaceInvitation(invitation.id); setWorkspaceInvitations(current => current.filter(item => item.id !== invitation.id)); setNotice(accept ? `Vous avez rejoint l’espace « ${invitation.workspaceName} ».` : 'Invitation refusée.'); }
    catch (error) { setError(message(error)); } finally { setPending(null); }
  }
  async function close() { setPending(-1); try { await onChanged(joinedId); onClose(); } catch (error) { setError(message(error)); } finally { setPending(null); } }
  return <Dialog title="Invitations" onClose={() => void close()} pending={pending !== null}><div className="form-body sharing-body"><div className="sharing-intro"><p>Rejoignez les espaces et projets auxquels vous êtes invité.</p><button className="icon-button" title="Actualiser les invitations" aria-label="Actualiser les invitations" disabled={loading || pending !== null} onClick={() => void load()}><ArrowsClockwise size={18} /></button></div><ErrorMessage>{error}</ErrorMessage>{notice && <p className="settings-notice" role="status">{notice}</p>}{loading ? <p role="status">Chargement des invitations…</p> : <>{workspaceInvitations.length > 0 && <ul className="sharing-list">{workspaceInvitations.map(invitation => <li key={invitation.id}><span className="sharing-icon"><Users size={21} /></span><div className="sharing-copy"><strong>{invitation.workspaceName}</strong><span>Espace · Invitation de {invitation.inviterName}</span></div><div className="sharing-actions"><button className="button subtle" disabled={pending !== null} aria-label={`Refuser l’espace ${invitation.workspaceName}`} onClick={() => void respondWorkspace(invitation, false)}>Refuser</button><button className="button primary" disabled={pending !== null} aria-label={`Accepter l’espace ${invitation.workspaceName}`} onClick={() => void respondWorkspace(invitation, true)}><Check size={15} />Accepter</button></div></li>)}</ul>}{invitations.length > 0 && <ul className="sharing-list">{invitations.map(invitation => <li key={invitation.id}><span className="sharing-icon"><EnvelopeSimple size={21} /></span><div className="sharing-copy"><strong>{invitation.projectName}</strong><span>Projet · Invitation de {invitation.inviterName}</span></div><div className="sharing-actions"><button className="button subtle" disabled={pending !== null} aria-label={`Refuser ${invitation.projectName}`} onClick={() => void respond(invitation, false)}>Refuser</button><button className="button primary" disabled={pending !== null} aria-label={`Accepter ${invitation.projectName}`} onClick={() => void respond(invitation, true)}><Check size={15} />Accepter</button></div></li>)}</ul>}{!workspaceInvitations.length && !invitations.length && !error && <p className="sharing-empty">Aucune invitation en attente.</p>}</>}</div></Dialog>;
}

export function ProjectMembersDialog({ project, onClose }: { project: Project; onClose: () => void }) {
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [invitations, setInvitations] = useState<ProjectInvitation[]>([]);
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const owner = project.role === 'owner';
  async function load() {
    setError('');
    const [nextMembers, nextInvitations] = await Promise.all([api.members(project.id), owner ? api.projectInvitations(project.id) : Promise.resolve([])]);
    setMembers(nextMembers); setInvitations(nextInvitations);
  }
  useEffect(() => { load().catch(error => setError(message(error))).finally(() => setLoading(false)); }, [project.id]);
  async function invite() {
    if (pending) return;
    setPending(true); setError(''); setNotice('');
    try { await api.invite(project.id, email.trim()); setEmail(''); await load(); setNotice('Invitation envoyée dans Circular. Aucun e-mail n’est envoyé.'); }
    catch (error) { setError(message(error)); }
    finally { setPending(false); }
  }
  async function remove(member: ProjectMember) {
    if (pending || !window.confirm(`Retirer l’accès de ${member.username} à ce projet ?`)) return;
    setPending(true); setError(''); setNotice('');
    try { await api.removeMember(project.id, member.id); await load(); setNotice('Accès au projet retiré.'); }
    catch (error) { setError(message(error)); }
    finally { setPending(false); }
  }
  async function cancel(invitation: ProjectInvitation) {
    if (pending) return;
    setPending(true); setError(''); setNotice('');
    try { await api.cancelInvitation(project.id, invitation.id); await load(); setNotice('Invitation annulée.'); }
    catch (error) { setError(message(error)); }
    finally { setPending(false); }
  }
  return <Dialog title={`Membres de ${project.name}`} onClose={onClose} pending={pending} dirty={!!email.trim()}><div className="form-body sharing-body"><p className="sharing-intro">{project.visibility === 'workspace' ? 'Les membres de l’espace ont accès aux tickets de ce projet. Leurs accès se gèrent depuis le menu de l’espace.' : 'Seuls le propriétaire et les membres acceptés ont accès aux tickets de ce projet.'} Les membres peuvent créer et modifier les tickets.</p><ErrorMessage>{error}</ErrorMessage>{notice && <p className="settings-notice" role="status">{notice}</p>}
    {owner && <form className="invite-form" onSubmit={event => { event.preventDefault(); void invite(); }} aria-busy={pending}><fieldset disabled={pending || loading}><label>Inviter par adresse e-mail<input type="email" required maxLength={254} pattern="[^\s@]+@epita\.fr" value={email} placeholder="prenom.nom@epita.fr" onChange={event => setEmail(event.target.value)} /></label><button className="button primary" type="submit"><EnvelopeSimple size={16} />Inviter</button></fieldset><p className="field-hint">La personne doit déjà avoir un compte Circular. Elle recevra une invitation dans l’application.</p></form>}
    {loading ? <p role="status">Chargement des membres…</p> : <><h3>Membres · {members.length}</h3><ul className="sharing-list">{members.map(member => <li key={member.id}><span className="account-avatar" aria-hidden="true">{member.username[0]?.toUpperCase()}</span><div className="sharing-copy"><strong>{member.username}</strong><span>{member.email}</span></div><span className="member-role">{member.inherited ? 'Via l’espace' : member.role === 'owner' ? 'Propriétaire' : 'Membre'}</span>{owner && member.canRemove && <button className="icon-button danger-icon" disabled={pending} aria-label={`Retirer ${member.username}`} title="Retirer l’accès au projet" onClick={() => void remove(member)}><X size={17} /></button>}</li>)}</ul>{owner && invitations.length > 0 && <><h3>Invitations en attente</h3><ul className="sharing-list">{invitations.map(invitation => <li key={invitation.id}><span className="sharing-icon"><Users size={19} /></span><div className="sharing-copy"><strong>{invitation.username}</strong><span>{invitation.email}</span></div><button className="button subtle" disabled={pending} aria-label={`Annuler l’invitation de ${invitation.email}`} onClick={() => void cancel(invitation)}>Annuler</button></li>)}</ul></>}</>}
  </div></Dialog>;
}
