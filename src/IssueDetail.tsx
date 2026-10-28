import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { ArrowsOutSimple, ChatCircle, ClockCounterClockwise, Copy, DotsThree, Link, PencilSimple, Star, Trash } from '@phosphor-icons/react';
import { api } from './api';
import type { Activity, Comment, Issue, IssueInput, Label, Project, Settings } from './types';
import { Dialog, ErrorMessage, message, StatusMark } from './ui';
import { IssueFields } from './IssueFields';
import './ticket-features.css';

const asInput = (issue: Issue): IssueInput => ({
  title: issue.title,
  description: issue.description,
  projectId: issue.projectId,
  status: issue.status,
  priority: issue.priority,
  labelIds: issue.labels.map(label => label.id),
  dueDate: issue.dueDate || null,
});
const date = (value: string) => new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(value));

type IssueDetailProps = {
  id: number;
  projects: Project[];
  labels: Label[];
  onClose: () => void;
  onSaved: () => void;
  onDeleted: () => void;
  onLabelCreated: (label: Label) => void;
  commentSubmit?: Settings['commentSubmit'];
  onDuplicate?: (issue: Issue) => void;
  onFavoriteChanged?: () => void;
  pageMode?: boolean;
  onPageModeChange?: (pageMode: boolean) => void;
};

export function IssueDetail({ id, projects, labels, onClose, onSaved, onDeleted, onLabelCreated, commentSubmit = 'ctrl_enter', onDuplicate, onFavoriteChanged, pageMode = false, onPageModeChange }: IssueDetailProps) {
  const [issue, setIssue] = useState<Issue>();
  const [data, setData] = useState<IssueInput>();
  const [comments, setComments] = useState<Comment[]>([]);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [activityError, setActivityError] = useState('');
  const [activityLoading, setActivityLoading] = useState(true);
  const [editing, setEditing] = useState<{ id: number; body: string; original: string } | null>(null);
  const [comment, setComment] = useState('');
  const [error, setError] = useState('');
  const [commentError, setCommentError] = useState('');
  const [pending, setPending] = useState(false);
  const [commentPending, setCommentPending] = useState(false);
  const [labelBusy, setLabelBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saved, setSaved] = useState(false);
  const [actionNote, setActionNote] = useState('');
  const [actionsOpen, setActionsOpen] = useState(false);
  const form = useRef<HTMLFormElement>(null);
  const commentInput = useRef<HTMLTextAreaElement>(null);
  const editingInput = useRef<HTMLTextAreaElement>(null);
  const actionsMenu = useRef<HTMLDetailsElement>(null);
  const dirty = !!issue && !!data && JSON.stringify(asInput(issue)) !== JSON.stringify(data);
  const busy = pending || commentPending || labelBusy;

  useEffect(() => {
    let active = true;
    setLoading(true);
    setIssue(undefined);
    setData(undefined);
    setComments([]);
    setSaved(false);
    setActionNote('');
    setError('');
    setCommentError('');
    setComment('');
    setEditing(null);
    setActivity([]);
    setActivityError('');
    setActivityLoading(true);
    Promise.all([api.issue(id), api.comments(id)]).then(([value, nextComments]) => {
      if (active) {
        setIssue(value);
        setData(asInput(value));
        setComments(nextComments);
      }
    }).catch(error => {
      if (active) setError(message(error));
    }).finally(() => {
      if (active) setLoading(false);
    });
    api.activity(id).then(value => { if (active) setActivity(value); }).catch(error => { if (active) setActivityError(message(error)); }).finally(() => { if (active) setActivityLoading(false); });
    return () => { active = false; };
  }, [id]);

  useEffect(() => {
    if (!loading) form.current?.querySelector<HTMLInputElement>('input')?.focus();
  }, [loading]);

  useEffect(() => { editingInput.current?.focus(); }, [editing?.id]);

  async function refreshActivity() {
    setActivityError('');
    try { setActivity(await api.activity(id)); }
    catch (error) { setActivityError(message(error)); }
  }

  async function save() {
    if (!data || busy || !form.current?.reportValidity()) return;
    setPending(true);
    setError('');
    setSaved(false);
    try {
      const value = await api.updateIssue(id, data);
      setIssue(value);
      setData(asInput(value));
      setSaved(true);
      onSaved();
      await refreshActivity();
    } catch (error) {
      setError(message(error));
    } finally {
      setPending(false);
    }
  }

  async function remove() {
    if (!issue || busy || !window.confirm(`Supprimer définitivement le ticket ${issue.identifier} et ses commentaires ?`)) return;
    setPending(true);
    setError('');
    try {
      await api.deleteIssue(id);
      onDeleted();
      onClose();
    } catch (error) {
      setError(message(error));
    } finally {
      setPending(false);
    }
  }

  async function publish() {
    if (!comment.trim() || busy) return;
    setCommentPending(true);
    setCommentError('');
    try {
      const value = await api.addComment(id, comment.trim());
      setComments(current => [...current, value]);
      setComment('');
      await refreshActivity();
    } catch (error) {
      setCommentError(message(error));
    } finally {
      setCommentPending(false);
    }
  }

  async function updateComment() {
    if (!editing || !editing.body.trim() || busy) return;
    setCommentPending(true);
    setCommentError('');
    try {
      const value = await api.updateComment(id, editing.id, editing.body.trim());
      setComments(current => current.map(item => item.id === value.id ? value : item));
      setEditing(null);
      await refreshActivity();
    } catch (error) { setCommentError(message(error)); }
    finally { setCommentPending(false); }
  }

  async function deleteComment(item: Comment) {
    if (busy || !window.confirm('Supprimer définitivement ce commentaire ?')) return;
    setCommentPending(true);
    setCommentError('');
    try {
      await api.deleteComment(id, item.id);
      setComments(current => current.filter(value => value.id !== item.id));
      if (editing?.id === item.id) setEditing(null);
      await refreshActivity();
    } catch (error) { setCommentError(message(error)); }
    finally { setCommentPending(false); }
  }

  function editComment(item: Comment) {
    if (editing && editing.body !== editing.original && !window.confirm('Abandonner la modification du commentaire en cours ?')) return;
    setEditing({ id: item.id, body: item.body, original: item.body });
    setCommentError('');
  }

  function commentKey(event: KeyboardEvent, submit: () => Promise<void>) {
    if (event.target instanceof HTMLTextAreaElement && event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && ((event.ctrlKey || event.metaKey) || commentSubmit === 'enter')) {
      event.preventDefault();
      event.stopPropagation();
      void submit();
    }
  }

  async function favorite() {
    if (!issue || busy) return;
    setPending(true);
    setError('');
    try {
      const value = await api.updateIssue(id, { isFavorite: !issue.isFavorite });
      setIssue(value);
      setActionNote(value.isFavorite ? 'Ticket ajouté aux favoris.' : 'Ticket retiré des favoris.');
      onFavoriteChanged?.();
      await refreshActivity();
    } catch (error) { setError(message(error)); }
    finally { setPending(false); }
  }

  async function duplicate() {
    if (busy || !onDuplicate) return;
    if ((dirty || comment.trim() || (editing && editing.body !== editing.original)) && !window.confirm('Dupliquer la dernière version enregistrée et abandonner les modifications en cours ?')) return;
    setPending(true);
    setError('');
    try { onDuplicate(await api.duplicateIssue(id)); }
    catch (error) { setError(message(error)); }
    finally { setPending(false); }
  }

  async function copy(value: string, confirmation: string) {
    setError('');
    if (actionsMenu.current) { actionsMenu.current.open = false; actionsMenu.current.querySelector('summary')?.focus(); }
    try { await navigator.clipboard.writeText(value); setActionNote(confirmation); }
    catch { setError('La copie dans le presse-papiers a échoué. Réessayez depuis un navigateur autorisant l’accès au presse-papiers.'); }
  }

  function focusComment() {
    commentInput.current?.focus({ preventScroll: true });
    commentInput.current?.scrollIntoView({ block: 'center' });
  }

  return (
    <Dialog title={issue ? `Ticket ${issue.identifier}` : 'Détail du ticket'} drawer={!pageMode} onClose={onClose} dirty={dirty || !!comment.trim() || !!(editing && editing.body !== editing.original)} pending={busy} onSave={save}>
      {loading ? <div className="loading-state" role="status">Chargement du ticket…</div> : !data || !issue ? (
        <div className="form-body"><ErrorMessage>{error}</ErrorMessage></div>
      ) : (
        <div className={pageMode ? 'issue-page-mode' : 'issue-drawer-mode'}>
          <div className="ticket-actionbar">
            <button type="button" className="button subtle ticket-favorite" aria-pressed={issue.isFavorite} disabled={busy} onClick={() => void favorite()}><Star size={16} weight={issue.isFavorite ? 'fill' : 'regular'} aria-hidden="true" />{issue.isFavorite ? 'Favori' : 'Ajouter aux favoris'}</button>
            <span className="ticket-action-note" role="status">{actionNote}</span>
            <details className="ticket-actions-menu" ref={actionsMenu} onToggle={event => setActionsOpen(event.currentTarget.open)} onKeyDown={event => { if (event.key === 'Escape' && actionsMenu.current?.open) { event.preventDefault(); event.stopPropagation(); actionsMenu.current.open = false; actionsMenu.current.querySelector('summary')?.focus(); } }}>
              <summary role="button" aria-expanded={actionsOpen} aria-label="Actions du ticket"><DotsThree size={22} aria-hidden="true" />Actions</summary>
              <div className="ticket-actions-popover">
                {onDuplicate && <button type="button" disabled={busy} onClick={() => void duplicate()}><Copy size={16} aria-hidden="true" />Dupliquer le ticket</button>}
                <button type="button" disabled={busy} onClick={() => void copy(issue.identifier, 'Identifiant copié.')}><Copy size={16} aria-hidden="true" />Copier l’identifiant</button>
                <button type="button" disabled={busy} onClick={() => void copy(`${location.origin}/?issue=${id}`, 'Lien copié.')}><Link size={16} aria-hidden="true" />Copier le lien</button>
                {onPageModeChange && <button type="button" disabled={busy} onClick={() => { if (actionsMenu.current) actionsMenu.current.open = false; onPageModeChange(!pageMode); }}><ArrowsOutSimple size={16} aria-hidden="true" />{pageMode ? 'Ouvrir en panneau' : 'Ouvrir en page'}</button>}
              </div>
            </details>
          </div>
          <form ref={form} className="detail-form" aria-busy={busy} onSubmit={event => { event.preventDefault(); void save(); }}>
            <div className="detail-overview">
              <div className="detail-meta">
                <StatusMark status={issue.status} />
                <span className="issue-identifier">{issue.identifier}</span>
                <time dateTime={issue.createdAt}>Créé le {date(issue.createdAt)}</time>
              </div>
              <button type="button" className="detail-comment-link" aria-label="Aller aux commentaires" disabled={busy} onClick={focusComment}>
                <ChatCircle size={16} aria-hidden="true" />
                Commentaires<span className="comment-count">{comments.length}</span>
              </button>
            </div>
            <fieldset className="form-body detail-fields" disabled={busy}>
              <ErrorMessage>{error}</ErrorMessage>
              <IssueFields
                data={data}
                setData={value => { setData(value); setSaved(false); }}
                projects={projects}
                labels={[...labels, ...issue.labels.filter(label => !labels.some(existing => existing.id === label.id))]}
                onLabelCreated={onLabelCreated}
                onLabelBusy={setLabelBusy}
              />
            </fieldset>
            <footer className="dialog-footer save-bar detail-save-bar">
              <button type="button" className="icon-button danger-icon" aria-label="Supprimer le ticket" title="Supprimer le ticket" disabled={busy} onClick={() => void remove()}>
                <Trash size={18} aria-hidden="true" />
              </button>
              <span className="detail-save-note" role="status">
                {dirty ? 'Modifications non enregistrées' : saved ? 'Modifications enregistrées' : 'Toutes les modifications sont enregistrées'}
              </span>
              <div className="detail-save">
                <button type="submit" className="button primary" disabled={busy || !dirty}>
                  {pending ? 'Enregistrement…' : 'Enregistrer'}
                </button>
              </div>
            </footer>
          </form>
          <section className="comment-section" aria-labelledby={`comment-heading-${id}`}>
            <header className="comment-heading comment-section-heading">
              <ChatCircle size={18} aria-hidden="true" />
              <h3 id={`comment-heading-${id}`}>Commentaires</h3>
              <span>{comments.length}</span>
            </header>
            <form
              className="comment-form"
              aria-busy={commentPending}
              onSubmit={event => { event.preventDefault(); void publish(); }}
              onKeyDown={event => commentKey(event, publish)}
            >
              <ErrorMessage>{commentError}</ErrorMessage>
              <label>
                <span className="field-label">Ajouter un commentaire</span>
                <textarea ref={commentInput} disabled={busy} rows={2} maxLength={10000} value={comment} onChange={event => setComment(event.target.value)} placeholder="Une précision, une avancée, une idée…" />
              </label>
              <div className="comment-actions">
                <span className="shortcut-hint">{commentSubmit === 'enter' ? 'Entrée pour publier · Maj + Entrée pour une nouvelle ligne' : 'Ctrl / ⌘ + Entrée pour publier'}</span>
                <button className="button" type="submit" disabled={!comment.trim() || busy}>
                  {commentPending ? 'Publication…' : 'Publier le commentaire'}
                </button>
              </div>
            </form>
            {comments.length ? (
              <ol className="comment-list">
                {comments.map(item => (
                  <li className="comment" key={item.id}>
                    <span className="avatar" aria-hidden="true">{item.author?.username[0]?.toUpperCase() || '?'}</span>
                    <div className="comment-main">
                      <div className="comment-byline"><strong>{item.author?.username || 'Ancien commentaire'}</strong><time dateTime={item.createdAt}>{date(item.createdAt)}</time><div className="comment-edit-actions">{item.canEdit && <button type="button" className="icon-button" aria-label="Modifier le commentaire" disabled={busy} onClick={() => editComment(item)}><PencilSimple size={14} aria-hidden="true" /></button>}{item.canDelete && <button type="button" className="icon-button danger-icon" aria-label="Supprimer le commentaire" disabled={busy} onClick={() => void deleteComment(item)}><Trash size={14} aria-hidden="true" /></button>}</div></div>
                      {editing?.id === item.id ? <form className="comment-edit-form" onSubmit={event => { event.preventDefault(); void updateComment(); }} onKeyDown={event => commentKey(event, updateComment)}><label><span className="field-label">Modifier le texte du commentaire</span><textarea ref={editingInput} required disabled={busy} rows={3} maxLength={10000} value={editing.body} onChange={event => setEditing({ ...editing, body: event.target.value })} /></label><div className="comment-actions"><button type="button" className="button subtle" disabled={busy} onClick={() => { if (editing.body === editing.original || window.confirm('Abandonner la modification du commentaire ?')) setEditing(null); }}>Annuler</button><button type="submit" className="button" disabled={busy || !editing.body.trim() || editing.body === editing.original}>Enregistrer le commentaire</button></div></form> : <p>{item.body}</p>}
                    </div>
                  </li>
                ))}
              </ol>
            ) : <p className="comment-empty">Aucun commentaire. Gardez ici une trace de vos décisions.</p>}
          </section>
          <section className="activity-section" aria-labelledby={`activity-heading-${id}`}>
            <header className="comment-heading"><ClockCounterClockwise size={18} aria-hidden="true" /><h3 id={`activity-heading-${id}`}>Historique</h3></header>
            <ErrorMessage>{activityError}</ErrorMessage>
            {activityError && <button type="button" className="button subtle" disabled={busy} onClick={() => void refreshActivity()}>Recharger l’historique</button>}
            {activityLoading ? <p className="field-hint" role="status">Chargement de l’historique…</p> : activity.length ? <ol className="activity-list">{activity.map(event => <li key={event.id}><span>{event.actor && <strong>{event.actor.username} · </strong>}{event.body}</span><time dateTime={event.createdAt}>{date(event.createdAt)}</time></li>)}</ol> : !activityError && <p className="comment-empty">Les prochains changements seront consignés ici.</p>}
          </section>
        </div>
      )}
    </Dialog>
  );
}
