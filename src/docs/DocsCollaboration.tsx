import { useEffect, useRef, useState } from 'react';
import { api as circularApi } from '../api';
import { Dialog, ErrorMessage, message } from '../ui';
import type { DocComment, DocNotification, DocsApi, DocsMember, DocPerson } from './api';

export function DocsAccessDialog({ api, workspace, close }: {
  api: DocsApi; workspace: { id: number; name: string }; close: () => void;
}) {
  const [members, setMembers] = useState<DocsMember[]>();
  const [pending, setPending] = useState(false);
  const [removing, setRemoving] = useState<DocPerson>();
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    let active = true;
    void api.accessMembers().then(result => { if (active) setMembers(result); })
      .catch(reason => { if (active) setError(message(reason)); });
    return () => { active = false; };
  }, [api]);

  async function change(person: DocPerson, role: 'reader' | 'editor') {
    setPending(true);
    setError('');
    setNotice('');
    try {
      await api.changeAccess(person.id, role);
      setMembers(current => current?.map(item => item.id === person.id ? { ...item, role } : item));
      setNotice('Accès Docs de ' + person.name + ' mis à jour.');
    } catch (reason) { setError(message(reason)); }
    finally { setPending(false); }
  }

  async function remove(person: DocPerson) {
    setPending(true);
    setError('');
    setNotice('');
    try {
      await circularApi.removeWorkspaceMember(workspace.id, person.id);
      setMembers(current => current?.filter(item => item.id !== person.id));
      setRemoving(undefined);
      setNotice(person.name + ' a été retiré de l’espace.');
    } catch (reason) { setError(message(reason)); }
    finally { setPending(false); }
  }

  return <Dialog title={'Accès Docs · ' + workspace.name} onClose={close} pending={pending}>
    <div className="form-body docs-collaboration-form">
      <p>Ces droits s’appliquent à toutes les pages de l’espace.</p>
      <ErrorMessage>{error}</ErrorMessage>
      {notice && <p role="status">{notice}</p>}
      {!members && !error && <p role="status">Chargement des accès…</p>}
      <ul className="docs-access-list">{members?.map(person => <li key={person.id}>
        <strong>{person.name}</strong>
        {person.role === 'owner' ? <span>Propriétaire</span> : <>
          <select aria-label={'Accès Docs de ' + person.name} value={person.role} disabled={pending || !!removing}
            onChange={event => void change(person, event.target.value === 'reader' ? 'reader' : 'editor')}>
            <option value="editor">Édition</option><option value="reader">Lecture</option>
          </select>
          <button className="button subtle" disabled={pending || !!removing}
            onClick={() => setRemoving(person)} aria-label={'Retirer ' + person.name + ' de l’espace'}>Retirer</button>
        </>}
      </li>)}</ul>
      {removing && <div className="docs-collaboration-form">
        <p>Retirer {removing.name} de l’espace {workspace.name} ? Cette action retire aussi ses droits sur les projets de l’espace.</p>
        <div className="docs-row">
          <button className="button" autoFocus disabled={pending} onClick={() => setRemoving(undefined)}>Annuler</button>
          <button className="button danger" disabled={pending} onClick={() => void remove(removing)}>Confirmer le retrait</button>
        </div>
      </div>}
    </div>
  </Dialog>;
}

export function DocsDiscussion({ api, pageId, canEdit, owner, userId, focusComment, close, refreshNotifications, refreshKey }: {
  api: DocsApi; pageId: string; canEdit: boolean; owner: boolean; userId: number;
  focusComment?: string; close: () => void; refreshNotifications: () => void; refreshKey: number;
}) {
  const [discussion, setDiscussion] = useState<{ items: DocComment[]; people: DocPerson[] }>();
  const [body, setBody] = useState('');
  const [mentionId, setMentionId] = useState<number | null>(null);
  const [editing, setEditing] = useState<DocComment>();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [retry, setRetry] = useState(0);
  const draftId = useRef('');
  const title = useRef<HTMLHeadingElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    void api.comments(pageId, controller.signal).then(result => {
      if (!controller.signal.aborted) {
        setDiscussion(result);
        setError('');
      }
    }).catch(reason => { if (!controller.signal.aborted) setError(message(reason)); });
    return () => controller.abort();
  }, [api, pageId, canEdit, retry, refreshKey]);

  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      if (!focusComment) title.current?.focus();
    });
    return () => cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    if (!focusComment || !discussion) return;
    const frame = requestAnimationFrame(() => {
      const target = document.getElementById('doc-comment-' + focusComment) ?? title.current;
      target?.focus();
    });
    return () => cancelAnimationFrame(frame);
  }, [focusComment, !!discussion]);

  function clear() {
    setBody('');
    setMentionId(null);
    setEditing(undefined);
    draftId.current = '';
  }

  async function save() {
    if (!body.trim() || !canEdit || pending) return;
    setPending(true);
    setError('');
    setNotice('');
    try {
      const data = { body, mentionId };
      draftId.current ||= crypto.randomUUID();
      const saved = editing ? await api.editComment(pageId, editing.id, { ...data, revision: editing.revision })
        : await api.createComment(pageId, draftId.current, data);
      setDiscussion(current => current && { ...current, items: current.items.some(item => item.id === saved.id)
        ? current.items.map(item => item.id === saved.id ? saved : item) : [...current.items, saved] });
      setNotice(editing ? 'Commentaire modifié.' : 'Commentaire publié.');
      clear();
      refreshNotifications();
    } catch (reason) { setError(message(reason)); }
    finally { setPending(false); }
  }

  async function remove(item: DocComment) {
    setPending(true);
    setError('');
    setNotice('');
    try {
      await api.deleteComment(pageId, item.id);
      setDiscussion(current => current && { ...current, items: current.items.filter(comment => comment.id !== item.id) });
      if (editing?.id === item.id) clear();
      setNotice('Commentaire supprimé.');
      title.current?.focus();
      refreshNotifications();
    } catch (reason) { setError(message(reason)); }
    finally { setPending(false); }
  }

  return <aside className="docs-discussion" aria-labelledby="docs-discussion-title" id="docs-discussion">
    <div className="docs-row">
      <h2 id="docs-discussion-title" ref={title} tabIndex={-1}>Commentaires</h2>
      <button className="button subtle" type="button" aria-label="Fermer les commentaires" onClick={close}>Fermer</button>
    </div>
    {!discussion && !error && <p role="status">Chargement des commentaires…</p>}
    {discussion && !discussion.items.length && <p>Aucun commentaire pour cette page.</p>}
    {discussion?.items.map(item => <article className="docs-comment" id={'doc-comment-' + item.id} key={item.id} tabIndex={-1}>
      <div className="docs-comment-author"><span className="account-avatar" aria-hidden="true">{item.author[0]?.toUpperCase()}</span><strong>{item.author}</strong></div>
      <p>{item.mentionName && <span className="docs-mention">@{item.mentionName} </span>}{item.body}</p>
      {canEdit && <div className="docs-comment-actions">
        {item.authorId === userId && <button className="button subtle" disabled={pending} onClick={() => {
          setEditing(item); setBody(item.body); setMentionId(item.mentionId); setError(''); textarea.current?.focus();
        }}>Modifier</button>}
        {(owner || item.authorId === userId) && <button className="button danger" disabled={pending} onClick={() => void remove(item)}>Supprimer</button>}
      </div>}
    </article>)}
    <ErrorMessage>{error}</ErrorMessage>
    {error && <button className="button" disabled={pending} onClick={() => setRetry(value => value + 1)}>Actualiser la discussion</button>}
    {notice && <p role="status">{notice}</p>}
    {discussion && canEdit && <form className="docs-collaboration-form" onSubmit={event => { event.preventDefault(); void save(); }}>
      <label>Votre commentaire<textarea ref={textarea} value={body} maxLength={2000} rows={3} required disabled={pending}
        onChange={event => setBody(event.target.value)} /></label>
      <label htmlFor="docs-mention-picker">Mentionner une personne</label>
      <select id="docs-mention-picker" value={mentionId ?? ''} disabled={pending}
        onChange={event => setMentionId(event.target.value ? Number(event.target.value) : null)}>
        <option value="">Choisir une personne</option>
        {discussion.people.map(person => <option key={person.id} value={person.id}>{person.name}</option>)}
      </select>
      <div className="docs-comment-actions">
        {editing && <button className="button" type="button" disabled={pending} onClick={() => { clear(); textarea.current?.focus(); }}>Annuler</button>}
        <button className="button primary" disabled={pending}>{pending ? 'Enregistrement…' : editing ? 'Enregistrer' : 'Publier'}</button>
      </div>
    </form>}
    {discussion && !canEdit && <p>Vous pouvez consulter les commentaires.</p>}
  </aside>;
}

export function DocsNotifications({ items, error, close, open, refresh }: {
  items?: DocNotification[]; error: string; close: () => void; open: (item: DocNotification) => void; refresh: () => void;
}) {
  return <Dialog title="Notifications Docs" onClose={close}>
    <div className="form-body docs-collaboration-form">
      <ErrorMessage>{error}</ErrorMessage>
      {error && <button className="button" onClick={refresh}>Réessayer</button>}
      {!items && !error && <p role="status">Chargement des notifications…</p>}
      {items?.length === 0 && <p>Aucune notification.</p>}
      {items?.map(item => <button type="button" className="button docs-notification" onClick={() => open(item)} key={item.commentId}>
        <span>{item.readAt ? '' : 'Non lu · '}{item.author} vous a mentionné dans un commentaire</span>
        <small>{item.title}</small>
      </button>)}
    </div>
  </Dialog>;
}
