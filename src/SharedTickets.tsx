import { useEffect, useRef, useState } from 'react';
import { request } from './api';
import { Dialog, ErrorMessage, message } from './ui';
import { STATUS_NAMES, type Activity, type Comment, type Issue } from './types';

type Page = { items: Array<Pick<Issue, 'id'|'identifier'|'title'|'status'>>; nextCursor: number | null };
type Ticket = { ticket: Issue; comments: Comment[]; activity: Activity[] };
type DocumentPage = { items: Array<{ id: string; title: string }>; nextCursor: string | null };
type Document = { id: string; title: string; markdown: string };

export function SharedTickets({ workspaceId, close }: { workspaceId: number; close: () => void }) {
  const [page, setPage] = useState<Page>();
  const [ticket, setTicket] = useState<Ticket>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [kind, setKind] = useState<'tickets'|'docs'>('tickets');
  const detailHeading = useRef<HTMLHeadingElement>(null);
  const path = '/workspaces/' + workspaceId + '/ticket-shares';

  useEffect(() => {
    const controller = new AbortController();
    void request<Page>(path, { signal: controller.signal }, workspaceId)
      .then(value => { if (!controller.signal.aborted) setPage(value); })
      .catch(cause => { if (!controller.signal.aborted) setError(message(cause)); });
    return () => controller.abort();
  }, [path, workspaceId]);
  useEffect(() => { if (ticket && kind === 'tickets') detailHeading.current?.focus(); }, [ticket, kind]);

  async function run(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError('');
    try { await action(); }
    catch (cause) { setError(message(cause)); }
    finally { setBusy(false); }
  }

  function open(id: number) {
    return run(async () => setTicket(await request<Ticket>(path + '/' + id, {}, workspaceId)));
  }

  function more() {
    if (!page?.nextCursor) return;
    const previous = page;
    return run(async () => {
      const next = await request<Page>(path + '?cursor=' + previous.nextCursor, {}, workspaceId);
      setPage({ items: [...previous.items, ...next.items], nextCursor: next.nextCursor });
    });
  }

  return <Dialog title="Partagés avec moi" onClose={close}>
    <div className="form-body">
      <div className="mcp-actions" role="group" aria-label="Ressources partagées">
        <button type="button" className="button" aria-pressed={kind === 'tickets'} onClick={() => setKind('tickets')}>Tickets</button>
        <button type="button" className="button" aria-pressed={kind === 'docs'} onClick={() => setKind('docs')}>Documents</button>
      </div>
      {kind === 'docs' ? <SharedDocuments workspaceId={workspaceId} /> : <>
      <ErrorMessage>{error}</ErrorMessage>
      {busy && <p role="status">Chargement…</p>}
      {ticket ? <>
        <button type="button" className="button" onClick={() => setTicket(undefined)}>Retour aux tickets partagés</button>
        <h3 ref={detailHeading} tabIndex={-1}>{ticket.ticket.identifier} · {ticket.ticket.title}</h3>
        <p>{STATUS_NAMES[ticket.ticket.status]} · Lecture seule</p><p className="planning-body">{ticket.ticket.description}</p>
        <section aria-label="Discussion"><h4>Discussion</h4>
          {ticket.comments.map(item => <p key={item.id}>{item.author?.displayName} · {item.body}</p>)}
          {!ticket.comments.length && <p>Aucun commentaire.</p>}
        </section>
        <section aria-label="Historique"><h4>Historique</h4>
          {ticket.activity.map(item => <p key={item.id}>{item.actor?.displayName} · {item.body}</p>)}
        </section>
      </> : <>
        {!page && !error && <p role="status">Chargement des tickets partagés…</p>}
        {page && !page.items.length && <p>Aucun ticket partagé.</p>}
        {page?.items.map(item => <button key={item.id} type="button" className="button" disabled={busy} onClick={() => void open(item.id)}>
          {item.identifier} · {item.title}
        </button>)}
        {page?.nextCursor && <button type="button" className="button" disabled={busy} onClick={() => void more()}>Charger la suite</button>}
      </>}
      </>}
    </div>
  </Dialog>;
}

function SharedDocuments({ workspaceId }: { workspaceId: number }) {
  const path = '/workspaces/' + workspaceId + '/document-shares';
  const [page, setPage] = useState<DocumentPage>();
  const [document, setDocument] = useState<Document>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const detailHeading = useRef<HTMLHeadingElement>(null);
  const attachments = document ? [...new Set([...document.markdown.matchAll(/\]\(\/attachments\/([0-9a-f-]{36})\)/gi)].map(match => match[1]))] : [];

  useEffect(() => {
    const controller = new AbortController();
    void request<DocumentPage>(path, { signal: controller.signal }, workspaceId)
      .then(value => { if (!controller.signal.aborted) setPage(value); })
      .catch(cause => { if (!controller.signal.aborted) setError(message(cause)); });
    return () => controller.abort();
  }, [path, workspaceId]);
  useEffect(() => { if (document) detailHeading.current?.focus(); }, [document]);

  async function load(id?: string) {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      if (id) setDocument(await request<Document>(path + '/' + id, {}, workspaceId));
      else if (page?.nextCursor) {
        const next = await request<DocumentPage>(path + '?cursor=' + page.nextCursor, {}, workspaceId);
        setPage({ items: [...page.items, ...next.items], nextCursor: next.nextCursor });
      }
    } catch (cause) { setError(message(cause)); }
    finally { setBusy(false); }
  }

  return <>
    <ErrorMessage>{error}</ErrorMessage>
    {(busy || (!page && !error)) && <p role="status">Chargement des documents partagés…</p>}
    {document ? <>
      <button type="button" className="button" onClick={() => setDocument(undefined)}>Retour aux documents partagés</button>
      <h3 ref={detailHeading} tabIndex={-1}>{document.title}</h3><p className="field-hint">Lecture seule</p><p className="planning-body">{document.markdown}</p>
      {attachments.length > 0 && <ul>{attachments.map((id, index) => <li key={id}><a href={'/api' + path + '/attachments/' + id}>Télécharger la pièce jointe {index + 1}</a></li>)}</ul>}
    </> : <>
      {page && !page.items.length && <p>Aucun document partagé.</p>}
      {page?.items.map(item => <button key={item.id} type="button" className="button" disabled={busy} onClick={() => void load(item.id)}>{item.title}</button>)}
      {page?.nextCursor && <button type="button" className="button" disabled={busy} onClick={() => void load()}>Charger la suite</button>}
    </>}
  </>;
}
