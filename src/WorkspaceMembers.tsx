import { useEffect, useState } from 'react';
import { Check, Copy, EnvelopeSimple, Link, Trash, X } from '@phosphor-icons/react';
import { api } from './api';
import type { User, Workspace, WorkspaceInvitation, WorkspaceInviteLink, WorkspaceMember } from './types';
import { Dialog, ErrorMessage, message } from './ui';

export function WorkspaceInviteForm({ workspace, onChanged, onPendingChange, onDraftChange }: { workspace: Workspace; onChanged?: () => Promise<void>; onPendingChange?: (pending: boolean) => void; onDraftChange?: (dirty: boolean) => void }) {
  const [emails, setEmails] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [results, setResults] = useState<{ email: string; error?: string }[]>([]);
  async function invite() {
    if (pending) return;
    setError('');
    const values = [...new Set(emails.split(/[\s,;]+/).map(email => email.trim().toLowerCase()).filter(Boolean))];
    if (!values.length || values.length > 20 || values.some(email => !/^[^\s@]+@epita\.fr$/.test(email))) { setError('Renseignez de 1 à 20 adresses @epita.fr, séparées par une ligne ou une virgule.'); return; }
    setPending(true); onPendingChange?.(true); setResults([]);
    const next: { email: string; error?: string }[] = [];
    for (const email of values) { try { await api.inviteToWorkspace(workspace.id, email); next.push({ email }); } catch (error) { next.push({ email, error: message(error) }); } }
    setResults(next);
    const remaining = next.filter(result => result.error).map(result => result.email).join('\n');
    setEmails(remaining); onDraftChange?.(!!remaining);
    try { await onChanged?.(); } catch (error) { setError(message(error)); }
    setPending(false); onPendingChange?.(false);
  }
  return <form aria-busy={pending} onSubmit={event => { event.preventDefault(); void invite(); }}><fieldset className="onboarding-fields" disabled={pending}><ErrorMessage>{error}</ErrorMessage><label>Adresses e-mail<textarea aria-label="Adresses e-mail" rows={3} value={emails} onChange={event => { setEmails(event.target.value); onDraftChange?.(!!event.target.value.trim()); }} placeholder={'prenom.nom@epita.fr\nautre.personne@epita.fr'} aria-describedby="workspace-invite-hint" /><span id="workspace-invite-hint" className="field-hint">Une adresse @epita.fr par ligne, ou séparée par une virgule. Les invitations seront visibles dans Circular à la connexion ; aucun e-mail n’est envoyé.</span></label><button className="button" type="submit" disabled={pending || !emails.trim()}><EnvelopeSimple size={16} />{pending ? 'Envoi…' : 'Envoyer les invitations'}</button></fieldset>{results.length > 0 && <ul className="workspace-invite-results" aria-live="polite">{results.map(result => <li className={result.error ? 'invite-error' : ''} key={result.email}>{result.error ? <X size={14} /> : <Check size={14} />}<span>{result.email} · {result.error || 'Invitation enregistrée'}</span></li>)}</ul>}</form>;
}

export function WorkspaceMembersDialog({ workspace, user, onClose, onLeft }: { workspace: Workspace; user: User; onClose: () => void; onLeft: () => Promise<void> }) {
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [invitations, setInvitations] = useState<WorkspaceInvitation[]>([]);
  const [links, setLinks] = useState<WorkspaceInviteLink[]>([]);
  const [generated, setGenerated] = useState<{ id: number; url: string }>();
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [draft, setDraft] = useState(false);
  const owner = workspace.role === 'owner';
  async function load() {
    const [nextMembers, nextInvitations, nextLinks] = await Promise.all([api.workspaceMembers(workspace.id), owner ? api.workspaceInvitations(workspace.id) : Promise.resolve([]), owner ? api.workspaceInviteLinks(workspace.id) : Promise.resolve([])]);
    setMembers(nextMembers); setInvitations(nextInvitations); setLinks(nextLinks);
  }
  useEffect(() => { let active = true; load().catch(error => { if (active) setError(message(error)); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, [workspace.id]);
  async function mutation(action: () => Promise<void>, text: string) { if (pending) return; setPending(true); setError(''); setNotice(''); try { await action(); await load(); setNotice(text); } catch (error) { setError(message(error)); } finally { setPending(false); } }
  async function remove(member: WorkspaceMember) {
    const self = member.id === user.id;
    if (pending || !window.confirm(self ? 'Quitter cet espace ? Vous perdrez l’accès à ses projets.' : `Retirer ${member.displayName || member.username} de cet espace et de ses projets ?`)) return;
    if (self) { setPending(true); setError(''); try { await api.removeWorkspaceMember(workspace.id, member.id); await onLeft(); } catch (error) { setError(message(error)); } finally { setPending(false); } }
    else await mutation(() => api.removeWorkspaceMember(workspace.id, member.id), 'Membre retiré de l’espace.');
  }
  async function createLink() { await mutation(async () => { const result = await api.createWorkspaceInviteLink(workspace.id); if (!result.token) throw new Error('Le lien n’a pas été retourné par le serveur.'); setGenerated({ id: result.id, url: `${location.origin}/#workspace-invite=${encodeURIComponent(result.token)}` }); }, 'Lien créé. Il expire dans 7 jours et peut être révoqué ci-dessous.'); }
  async function copy() { if (!generated) return; try { await navigator.clipboard.writeText(generated.url); setNotice('Lien d’invitation copié.'); } catch { setError('La copie a échoué. Autorisez l’accès au presse-papiers dans votre navigateur.'); } }
  const shortDate = (date: string) => new Date(date).toLocaleDateString('fr-FR');
  return <Dialog title={`Membres de l’espace ${workspace.name}`} onClose={onClose} pending={pending} dirty={draft}><div className="form-body sharing-body"><p className="sharing-intro">Les membres de l’espace peuvent collaborer sur ses projets. Les invités disposent uniquement des accès aux projets qui leur ont été partagés.</p><ErrorMessage>{error}</ErrorMessage>{notice && <p className="settings-notice" role="status">{notice}</p>}{loading ? <p role="status">Chargement des membres…</p> : <>
    {owner && <WorkspaceInviteForm workspace={workspace} onChanged={load} onPendingChange={setPending} onDraftChange={setDraft} />}
    <h3>Membres · {members.length}</h3><ul className="sharing-list">{members.map(member => <li key={member.id}><span className="account-avatar" aria-hidden="true">{(member.displayName || member.username)[0]?.toUpperCase()}</span><div className="sharing-copy"><strong>{member.displayName || member.username}</strong><span>{member.email}{member.title ? ` · ${member.title}` : ''}</span></div><span className="member-role">{member.role === 'owner' ? 'Propriétaire' : member.role === 'guest' ? 'Invité' : 'Membre'}</span>{member.role !== 'owner' && (owner || member.id === user.id) && <button className="icon-button danger-icon" disabled={pending} aria-label={member.id === user.id ? 'Quitter cet espace' : `Retirer ${member.displayName || member.username}`} onClick={() => void remove(member)}><X size={17} /></button>}</li>)}</ul>
    {owner && invitations.length > 0 && <><h3>Invitations en attente</h3><ul className="sharing-list">{invitations.map(invitation => <li key={invitation.id}><div className="sharing-copy"><strong>{invitation.email}</strong><span>Expire le {shortDate(invitation.expiresAt)}</span></div><button className="button subtle" disabled={pending} aria-label={`Annuler l’invitation de ${invitation.email}`} onClick={() => void mutation(() => api.cancelWorkspaceInvitation(workspace.id, invitation.id), 'Invitation annulée.')}>Annuler</button></li>)}</ul></>}
    {owner && <><h3>Liens d’invitation</h3><p className="field-hint">Toute personne possédant un lien valide et un compte @epita.fr peut rejoindre l’espace. Partagez-le uniquement avec votre équipe.</p><div className="sharing-actions"><button className="button" disabled={pending} onClick={() => void createLink()}><Link size={16} />Générer un lien</button>{generated && <button className="button" disabled={pending} onClick={() => void copy()}><Copy size={16} />Copier le lien d’invitation</button>}</div>{links.length > 0 && <ul className="sharing-list">{links.map(link => <li key={link.id}><div className="sharing-copy"><strong>Lien créé le {shortDate(link.createdAt)}</strong><span>Expire le {shortDate(link.expiresAt)}</span></div><button className="icon-button danger-icon" disabled={pending} aria-label={`Révoquer le lien ${link.id}`} onClick={() => void mutation(async () => { await api.revokeWorkspaceInviteLink(workspace.id, link.id); if (generated?.id === link.id) setGenerated(undefined); }, 'Lien révoqué.')}><Trash size={16} /></button></li>)}</ul>}</>}
  </>}</div></Dialog>;
}
