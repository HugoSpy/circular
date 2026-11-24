import { useEffect, useRef, useState } from 'react';
import { Trash } from '@phosphor-icons/react';
import { ApiError } from '../api';
import { Dialog, ErrorMessage, message } from '../ui';
import { DocsForm } from './DocsForms';
import type { DocsApi, DocPage, DocRevision, RevisionSummary, TrashEntry, TrashRestore } from './api';

const dateFormat = new Intl.DateTimeFormat('fr-FR', { dateStyle: 'medium', timeStyle: 'short' });
const dateLabel = (date: string | null) => date ? dateFormat.format(new Date(date)) : 'Date inconnue';

export function DocsHistory({ pageId, api, close, mayReplace, restored }: {
  pageId: string; api: DocsApi; close: () => void; mayReplace: () => boolean; restored: (page: DocPage) => void;
}) {
  const [current, setCurrent] = useState<DocPage>();
  const [items, setItems] = useState<RevisionSummary[]>([]);
  const [next, setNext] = useState<number | null>(null);
  const [selected, setSelected] = useState<number>();
  const [detail, setDetail] = useState<DocRevision>();
  const [loading, setLoading] = useState(true);
  const [paging, setPaging] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [error, setError] = useState('');
  const [detailError, setDetailError] = useState('');
  const [retry, setRetry] = useState(0);
  const [detailRetry, setDetailRetry] = useState(0);
  const cancel = useRef<HTMLButtonElement>(null);
  const restoreButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    void Promise.all([api.page(pageId), api.revisions(pageId)]).then(([page, versions]) => {
      if (!active) return;
      setCurrent(page);
      setItems(versions.items);
      setNext(versions.nextBefore);
      setSelected(previous => previous ?? page.revision);
      setConflict(false);
    }).catch(reason => { if (active) setError(message(reason)); }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [api, pageId, retry]);

  useEffect(() => {
    if (selected === undefined || selected === current?.revision) return;
    let active = true;
    setDetailError('');
    void api.revision(pageId, selected).then(result => {
      if (active) setDetail(result);
    }).catch(reason => { if (active) setDetailError(message(reason)); });
    return () => { active = false; };
  }, [api, current?.revision, detailRetry, pageId, selected]);

  useEffect(() => { if (confirm) cancel.current?.focus(); }, [confirm]);

  async function loadMore() {
    if (!next || paging) return;
    setPaging(true); setError('');
    try {
      const result = await api.revisions(pageId, next);
      setItems(previous => [...previous, ...result.items]);
      setNext(result.nextBefore);
    } catch (reason) { setError(message(reason)); }
    finally { setPaging(false); }
  }

  const chosen = selected === current?.revision ? current : detail?.revision === selected ? detail : undefined;

  async function restore() {
    if (!current || !chosen || restoring || !mayReplace()) return;
    setRestoring(true); setError('');
    try {
      const page = await api.restoreRevision(pageId, chosen.revision, current.revision);
      restored(page);
      close();
    } catch (reason) {
      setConfirm(false);
      const changed = reason instanceof ApiError && reason.status === 409;
      setConflict(changed);
      setError(changed ? 'La page a changé depuis l’ouverture de l’historique. Votre sélection et votre brouillon sont conservés.' : message(reason));
    } finally { setRestoring(false); }
  }

  function cancelRestore() {
    setConfirm(false);
    requestAnimationFrame(() => restoreButton.current?.focus());
  }

  return <Dialog title={confirm ? 'Restaurer la révision ' + chosen?.revision : 'Historique de la page'}
    onClose={close} pending={restoring}>
    <div className="form-body">
      {confirm ? <p>Le titre et le contenu sélectionnés seront enregistrés dans une nouvelle révision. Les versions précédentes resteront dans l’historique.</p>
        : <>
          {loading && <p role="status">Chargement de l’historique…</p>}
          {current && !loading && <div className="docs-history">
            <div className="docs-history-list" aria-label="Révisions">
              {items.map(item => <button key={item.revision} className="button" aria-pressed={selected === item.revision}
                onClick={() => setSelected(item.revision)}>
                <span>Révision {item.revision}{item.revision === current.revision ? ' · Actuelle' : ''}</span>
                <small>{item.author || 'Auteur inconnu'} · {dateLabel(item.createdAt)}</small>
              </button>)}
              {next && <button className="button" onClick={() => void loadMore()} disabled={paging}>
                {paging ? 'Chargement…' : 'Révisions précédentes'}
              </button>}
              {!items.length && <p>Aucune révision à afficher.</p>}
            </div>
            <div className="docs-history-compare">
              <article><h3>Version actuelle</h3><strong>{current.title}</strong><pre>{current.markdown || 'Page vide.'}</pre></article>
              <article><h3>Révision sélectionnée</h3>
                {chosen ? <><strong>{chosen.title}</strong><pre>{chosen.markdown || 'Page vide.'}</pre></>
                  : detailError ? <><ErrorMessage>{detailError}</ErrorMessage>
                    <button className="button" onClick={() => { setDetailError(''); setDetailRetry(value => value + 1); }}>Réessayer</button></>
                    : <p role="status">Chargement de la révision…</p>}
              </article>
            </div>
          </div>}
          <ErrorMessage>{error}</ErrorMessage>
          {conflict && <button className="button" onClick={() => setRetry(value => value + 1)}>Actualiser la comparaison</button>}
          {error && !current && !loading && <button className="button" onClick={() => setRetry(value => value + 1)}>Réessayer</button>}
        </>}
    </div>
    <div className="dialog-footer docs-lifecycle-footer">
      {confirm ? <>
        <button ref={cancel} className="button" onClick={cancelRestore} disabled={restoring}>Annuler</button>
        <button className="button primary" onClick={() => void restore()} disabled={restoring}>
          {restoring ? 'Restauration…' : 'Restaurer la révision'}
        </button>
      </> : <>
        <button className="button" onClick={close}>Fermer</button>
        {current && chosen && chosen.revision !== current.revision && !conflict &&
          <button ref={restoreButton} className="button primary" onClick={() => setConfirm(true)}>
            Restaurer la révision {chosen.revision}
          </button>}
      </>}
    </div>
  </Dialog>;
}

export function DocsTrash({ api, restored }: { api: DocsApi; restored: (result: TrashRestore) => void }) {
  const [entries, setEntries] = useState<TrashEntry[]>();
  const [selection, setSelection] = useState<TrashEntry>();
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setError('');
    void api.trash().then(result => {
      if (active) setEntries(result);
    }).catch(reason => { if (active) setError(message(reason)); });
    return () => { active = false; };
  }, [api, retry]);

  useEffect(() => { document.getElementById('workspace')?.focus({ preventScroll: true }); }, []);

  return <>
    <div className="docs-heading"><div><span className="docs-heading-icon"><Trash size={23} aria-hidden /></span>
      <h1 id="workspace" tabIndex={-1}>Corbeille</h1></div></div>
    <p className="docs-lifecycle-note">Les pages et leurs sous-pages peuvent être restaurées ensemble.</p>
    <ErrorMessage>{error}</ErrorMessage>
    {error && <button className="button" onClick={() => setRetry(value => value + 1)}>Réessayer</button>}
    {!entries && !error && <p role="status">Chargement de la corbeille…</p>}
    {entries && !entries.length && <p className="docs-trash-empty">La corbeille est vide.</p>}
    {!!entries?.length && <ul className="docs-trash-list">
      {entries.map(entry => <li key={entry.id}>
        <div>
          <strong>{entry.title}</strong>
          <small>{entry.count} {entry.count === 1 ? 'page' : 'pages'} · {dateLabel(entry.trashedAt)}</small>
          {entry.parentId && <small>Parent d’origine · {entry.parentTitle || 'Page indisponible'}{entry.parentTitle && !entry.parentAvailable ? ' (indisponible)' : ''}</small>}
        </div>
        <button className="button" aria-label={'Restaurer ' + entry.title} onClick={() => setSelection(entry)}>Restaurer</button>
      </li>)}
    </ul>}
    {selection && <DocsForm title="Restaurer la page" action="Restaurer" close={() => setSelection(undefined)}
      submit={async () => restored(await api.restoreTrash(selection.id))}>
      <p>{selection.parentId && !selection.parentAvailable
        ? <>Le parent d’origine est indisponible. « {selection.title} » sera restaurée à la racine de Docs.</>
        : <>« {selection.title} » et les sous-pages de cette mise à la corbeille seront restaurées.</>}</p>
    </DocsForm>}
  </>;
}
