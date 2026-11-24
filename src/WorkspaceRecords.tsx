import { useEffect, useRef, useState } from 'react';
import { request } from './api';
import { Dialog, ErrorMessage, message } from './ui';
import type { Project } from './types';

const sections = [
  { label: 'Feuille de route', kinds: [
    ['initiative', 'Initiatives', 'initiative'], ['milestone', 'Jalons', 'jalon'], ['cycle', 'Cycles', 'cycle'],
    ['update', 'Bilans', 'bilan'], ['triage', 'Permanences', 'permanence'],
  ] },
  { label: 'Clients et demandes', kinds: [['customer', 'Clients', 'client'], ['request', 'Demandes', 'demande']] },
  { label: 'Releases et revues', kinds: [
    ['pipeline', 'Pipelines', 'pipeline'], ['release', 'Releases', 'release'],
    ['release_note', 'Notes de version', 'note de version'], ['pull_link', 'Revues GitHub', 'lien de pull request'], ['review_criterion', 'Critères de revue', 'critère de revue'],
  ] },
  { label: 'Contexte des assistants', kinds: [
    ['instruction', 'Consignes', 'consigne'], ['learning', 'Notes vérifiées', 'note'], ['friction', 'Blocages', 'blocage'],
  ] },
] as const;

type Kind = typeof sections[number]['kinds'][number][0];
const stateNames = { planned: 'Planifié', active: 'En cours', review: 'En revue', done: 'Terminé', canceled: 'Annulé' };
type State = keyof typeof stateNames;
type Draft = {
  title: string; body: string; state: State;
  projectId: number | null; ticketId: number | null; parentId: string | null;
  sourceUrl: string | null; startsOn: string | null; endsOn: string | null;
};
type Item = Draft & { id: string; kind: Kind; revision: number; updatedAt: string; archivedAt: string | null; createdBy: number; helpfulCount: number };
type Page = { items: Item[]; nextCursor: string | null };
type PullPage = { pull: { title: string; sha: string; base: string; state: string; merged: boolean };
  files: { path: string; status: string; patch: string }[]; nextPage: number | null };
const blank: Draft = { title: '', body: '', state: 'planned', projectId: null, ticketId: null, parentId: null, sourceUrl: null, startsOn: null, endsOn: null };
const hasProject = new Set<Kind>(['initiative', 'milestone', 'cycle', 'update', 'triage', 'request', 'pipeline', 'release', 'release_note', 'review_criterion', 'pull_link', 'friction']);
const hasTicket = new Set<Kind>(['request', 'release', 'pull_link', 'friction']);
const parentLabels: Partial<Record<Kind, string>> = {
  initiative: 'Identifiant de l’initiative parente', update: 'Identifiant de l’initiative ou du jalon',
  request: 'Identifiant du client', release: 'Identifiant du pipeline', release_note: 'Identifiant du pipeline ou de la release',
};

export function WorkspaceRecords({ workspaceId, projects, userId, owner }: { workspaceId: number; projects: Project[]; userId: number; owner: boolean }) {
  const [section, setSection] = useState(0);
  const [kind, setKind] = useState<Kind>('initiative');
  const [query, setQuery] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState<Page>();
  const [listError, setListError] = useState('');
  const [edit, setEdit] = useState<Item | 'new'>();
  const [draft, setDraft] = useState<Draft>(blank);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const [parentOptions, setParentOptions] = useState<Item[]>([]);
  const [showArchived, setShowArchived] = useState(false);
  const [archive, setArchive] = useState<Item>();
  const [archiveApproved, setArchiveApproved] = useState(false);
  const [pull, setPull] = useState<Item>();
  const fallback = useRef<HTMLButtonElement>(null);
  const path = '/workspaces/' + workspaceId + '/records/' + kind;
  const sectionInfo = sections[section];
  const noun = sectionInfo.kinds.find(option => option[0] === kind)?.[2];
  const scopeKey = useRef(path);
  scopeKey.current = path;

  function list(signal?: AbortSignal, cursor?: string) {
    const params = new URLSearchParams({ q: search, include_archived: String(showArchived) });
    if (cursor) params.set('cursor', cursor);
    return request<Page>(path + '?' + params, { signal }, workspaceId);
  }

  useEffect(() => {
    const controller = new AbortController();
    setPage(undefined);
    setListError('');
    void list(controller.signal).then(result => { if (!controller.signal.aborted) setPage(result); })
      .catch(cause => { if (!controller.signal.aborted) setListError(message(cause)); });
    return () => controller.abort();
  }, [path, search, showArchived, refresh]);

  useEffect(() => {
    if (!edit || !parentLabels[kind]) return;
    const controller = new AbortController();
    const kinds = kind === 'request' ? ['customer'] : kind === 'release' ? ['pipeline']
      : kind === 'release_note' ? ['pipeline', 'release'] : kind === 'update' ? ['initiative', 'milestone'] : ['initiative'];
    setParentOptions([]);
    void Promise.all(kinds.map(parent => request<Page>('/workspaces/' + workspaceId + '/records/' + parent,
      { signal: controller.signal }, workspaceId))).then(pages => {
      if (!controller.signal.aborted) setParentOptions(pages.flatMap(value => value.items));
    }).catch(() => { /* The exact identifier remains available. */ });
    return () => controller.abort();
  }, [edit, kind, workspaceId]);

  function select(next: Kind) {
    setKind(next);
    setSearch('');
    setQuery('');
    setNotice('');
  }

  function open(item: Item | 'new') {
    if (item === 'new') setDraft(blank);
    else {
      const { title, body, state, projectId, ticketId, parentId, sourceUrl, startsOn, endsOn } = item;
      setDraft({ title, body, state, projectId, ticketId, parentId, sourceUrl, startsOn, endsOn });
    }
    setError('');
    setEdit(item);
  }

  async function save() {
    if (!edit || busy) return;
    setBusy(true);
    setError('');
    try {
      const data = edit === 'new' ? { record: draft } : { id: edit.id, revision: edit.revision, record: draft };
      const saved = await request<Item>(path, { method: 'POST', body: JSON.stringify(data) }, workspaceId);
      setEdit(undefined);
      setNotice('Enregistré · ' + saved.title);
      setRefresh(value => value + 1);
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  }

  async function more() {
    if (!page?.nextCursor || loadingMore) return;
    const previous = page;
    setLoadingMore(true);
    try {
      const next = await list(undefined, page.nextCursor);
      if (scopeKey.current === path) setPage(current => current === previous ? { items: [...previous.items, ...next.items], nextCursor: next.nextCursor } : current);
    } catch (cause) {
      if (scopeKey.current === path) setListError(message(cause));
    } finally {
      setLoadingMore(false);
    }
  }

  async function confirmArchive() {
    if (!archive || !archiveApproved || busy) return;
    setBusy(true);
    setError('');
    try {
      await request<Item>(path + '/' + archive.id + '/archive', { method: 'POST',
        body: JSON.stringify({ revision: archive.revision, approved: true }) }, workspaceId);
      setNotice('Archivé · ' + archive.title);
      setArchive(undefined);
      setRefresh(value => value + 1);
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  }

  return <section className="planning-workspace" aria-label="Pilotage de l’espace">
    <nav className="mcp-actions" aria-label="Domaines du pilotage">
      {sections.map((group, index) => <button key={group.label} type="button" className={'button' + (index === section ? ' primary' : '')}
        aria-pressed={index === section} onClick={() => { setSection(index); select(group.kinds[0][0]); }}>{group.label}</button>)}
    </nav>
    <div className="mcp-actions" role="group" aria-label={sectionInfo.label}>
      {sectionInfo.kinds.map(([id, label]) => <button key={id} type="button" className="button" aria-pressed={kind === id} onClick={() => select(id)}>{label}</button>)}
    </div>
    <form className="mcp-actions planning-search" onSubmit={event => { event.preventDefault(); setSearch(query.trim()); }}>
      <label className="screen-reader-only" htmlFor="planning-query">Rechercher dans la rubrique</label>
      <input id="planning-query" type="search" maxLength={200} value={query} onChange={event => setQuery(event.target.value)} placeholder="Rechercher dans la rubrique" />
      <button className="button" type="submit">Rechercher</button>
      <button ref={fallback} className="button primary" onClick={() => open('new')} type="button">Créer</button>
    </form>
    <label className="planning-option"><input type="checkbox" checked={showArchived} onChange={event => setShowArchived(event.target.checked)} />Afficher les éléments archivés</label>
    {notice && <p role="status" className="settings-notice">{notice}</p>}
    <ErrorMessage>{listError}</ErrorMessage>
    {listError && <button className="button" onClick={() => setRefresh(value => value + 1)}>Réessayer</button>}
    {!page && !listError && <p role="status" className="field-hint">Chargement…</p>}
    {page && !page.items.length && <p className="field-hint">Aucun élément dans cette rubrique.</p>}
    {page && <div className="planning-list">{page.items.map(item => <article className="planning-entry" key={item.id}>
      <div><h2>{item.title}</h2><p className="field-hint">{stateNames[item.state]}{item.archivedAt ? ' · Archivé' : ''}</p>
        {item.body && <p className="planning-body">{item.body}</p>}
        {item.kind === 'learning' && <p className="field-hint">Avis utiles · {item.helpfulCount}</p>}
        {item.sourceUrl && <p><a href={item.sourceUrl} target="_blank" rel="noreferrer">Source</a></p>}
        {item.kind === 'pull_link' && item.sourceUrl && <button className="button" type="button" onClick={() => setPull(item)}>Consulter les modifications GitHub</button>}
        <details><summary>Références</summary><dl>
          <dt>Identifiant</dt><dd>{item.id}</dd>
          <dt>Révision</dt><dd>{item.revision}</dd>
          {item.projectId && <><dt>Projet</dt><dd>{projects.find(project => project.id === item.projectId)?.name || item.projectId}</dd></>}
          {item.ticketId && <><dt>Ticket</dt><dd>{item.ticketId}</dd></>}
        </dl></details>
      </div>
      {!item.archivedAt && (owner || item.createdBy === userId) && <div className="mcp-actions">
        <button className="button" onClick={() => open(item)} aria-label={'Modifier ' + item.title}>Modifier</button>
        <button className="button" onClick={() => { setArchive(item); setArchiveApproved(false); setError(''); }} aria-label={'Archiver ' + item.title}>Archiver</button>
      </div>}
    </article>)}</div>}
    {page?.nextCursor && <button className="button" disabled={loadingMore} onClick={() => void more()}>Charger la suite</button>}
    {edit && <Dialog title={edit === 'new' ? 'Créer · ' + noun : 'Modifier · ' + noun} pending={busy} onClose={() => setEdit(undefined)} fallbackFocus={fallback}>
      <form onSubmit={event => { event.preventDefault(); void save(); }}>
        <fieldset className="form-body" disabled={busy}>
          <label>Titre<input required maxLength={240} value={draft.title} onChange={event => setDraft({ ...draft, title: event.target.value })} /></label>
          <label>Description<textarea rows={4} maxLength={20000} value={draft.body} onChange={event => setDraft({ ...draft, body: event.target.value })} /></label>
          <label>Statut<select value={draft.state} onChange={event => setDraft({ ...draft, state: event.target.value as State })}>
            {Object.entries(stateNames).map(([value, name]) => <option value={value} key={value}>{name}</option>)}
          </select></label>
          {hasProject.has(kind) && <label>Projet<select value={draft.projectId ?? ''} required={kind === 'milestone' || kind === 'pull_link'} disabled={edit !== 'new'}
            onChange={event => setDraft({ ...draft, projectId: Number(event.target.value) || null })}>
            <option value="">Aucun projet</option>{projects.map(project => <option value={project.id} key={project.id}>{project.name}</option>)}
          </select></label>}
          {hasTicket.has(kind) && <label>Identifiant numérique du ticket<input type="number" min={1} required={kind === 'pull_link'} value={draft.ticketId ?? ''}
            onChange={event => setDraft({ ...draft, ticketId: Number(event.target.value) || null })} /></label>}
          {parentLabels[kind] && <label>{parentLabels[kind]}<input list="planning-parent-options" required={kind === 'release' || kind === 'release_note'}
            value={draft.parentId ?? ''} onChange={event => setDraft({ ...draft, parentId: event.target.value || null })} />
            <datalist id="planning-parent-options">{parentOptions.filter(item => item.id !== (edit === 'new' ? null : edit.id)).map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</datalist>
          </label>}
          <label>{kind === 'pull_link' ? 'Lien de la pull request GitHub' : 'Lien source'}<input type="url" required={kind === 'pull_link'} maxLength={2048} value={draft.sourceUrl ?? ''} onChange={event => setDraft({ ...draft, sourceUrl: event.target.value || null })} /></label>
          {hasProject.has(kind) && <div className="mcp-actions planning-dates">
            <label>Date de début<input type="date" value={draft.startsOn ?? ''} onChange={event => setDraft({ ...draft, startsOn: event.target.value || null })} /></label>
            <label>Date de fin<input type="date" min={draft.startsOn || undefined} value={draft.endsOn ?? ''} onChange={event => setDraft({ ...draft, endsOn: event.target.value || null })} /></label>
          </div>}
          <ErrorMessage>{error}</ErrorMessage>
        </fieldset>
        <div className="dialog-footer"><button type="button" className="button" disabled={busy} onClick={() => setEdit(undefined)}>Annuler</button>
          <button type="submit" className="button primary" disabled={busy || !draft.title.trim()}>Enregistrer</button></div>
      </form>
    </Dialog>}
    {archive && <Dialog title="Confirmer l’archivage" pending={busy} onClose={() => setArchive(undefined)} fallbackFocus={fallback}>
      <div className="form-body"><p>{archive.title} sera retiré des listes actives.</p><label className="planning-option"><input type="checkbox" checked={archiveApproved} disabled={busy} onChange={event => setArchiveApproved(event.target.checked)} />Je confirme l’archivage de cet élément.</label><ErrorMessage>{error}</ErrorMessage></div>
      <div className="dialog-footer"><button type="button" className="button" disabled={busy} onClick={() => setArchive(undefined)}>Annuler</button>
        <button type="button" className="button danger" disabled={busy || !archiveApproved} onClick={() => void confirmArchive()}>Archiver</button></div>
    </Dialog>}
    {pull?.sourceUrl && <GithubPullPreview workspaceId={workspaceId} source={pull.sourceUrl} close={() => setPull(undefined)} />}
  </section>;
}

function GithubPullPreview({ workspaceId, source, close }: { workspaceId: number; source: string; close: () => void }) {
  const [data, setData] = useState<PullPage>();
  const [error, setError] = useState('');
  const [page, setPage] = useState(1);

  useEffect(() => {
    const parsed = /^https:\/\/github\.com\/([\w.-]+\/[\w.-]+)\/pull\/(\d+)$/.exec(source);
    if (!parsed) { setError('Le lien GitHub de cet élément est invalide.'); return; }
    const controller = new AbortController();
    const params = new URLSearchParams({ repository: parsed[1], number: parsed[2], page: String(page) });
    setData(undefined);
    setError('');
    void request<PullPage>(`/workspaces/${workspaceId}/github/pull?${params}`, { signal: controller.signal }, workspaceId)
      .then(result => { if (!controller.signal.aborted) setData(result); })
      .catch(cause => { if (!controller.signal.aborted) setError(message(cause)); });
    return () => controller.abort();
  }, [source, workspaceId, page]);

  return <Dialog title="Modifications de la pull request" onClose={close}>
    <div className="form-body">
      <ErrorMessage>{error}</ErrorMessage>
      {!data && !error && <p role="status">Chargement depuis GitHub…</p>}
      {data && <>
        <h3>{data.pull.title}</h3>
        <p>Branche cible · {data.pull.base}</p><p>Révision · <code>{data.pull.sha}</code></p>
        {!data.files.length && <p>Aucun fichier modifié.</p>}
        {data.files.map(file => <details key={file.path} className="planning-patch"><summary>{file.path} · {file.status}</summary>
          <pre>{file.patch || 'GitHub ne fournit pas de diff textuel pour ce fichier.'}</pre>
        </details>)}
        <div className="mcp-actions">
          <button className="button" type="button" disabled={page === 1} onClick={() => setPage(page - 1)}>Fichiers précédents</button>
          <button className="button" type="button" disabled={!data.nextPage} onClick={() => { if (data.nextPage) setPage(data.nextPage); }}>Fichiers suivants</button>
        </div>
      </>}
    </div>
  </Dialog>;
}
