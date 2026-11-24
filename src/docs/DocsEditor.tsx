import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { ApiError } from '../api';
import { Dialog, ErrorMessage, message } from '../ui';

import { EmbeddedViewPicker, EmbeddedViews } from './DocsEmbeddedViewPicker';
import { DocsForm } from './DocsForms';
import { attachmentHref, escapeLabel, type AttachmentKind, type AttachmentRequest, type CollectionSummary, type DocPage, type DocsApi, type EmbeddedRequest, type LinkRequest, type LinkValue, type OpenDoc, type PageSummary } from './api';
import './markdown.css';
import type { OpenGalleryPage } from './gallery-navigation';

const MarkdownVisual = lazy(() => import('./MarkdownVisual').then(module => ({ default: module.MarkdownVisual })));

type Guard = (guard: (() => boolean) | null) => void;

export function usePageDraft(page: DocPage, api: DocsApi, registerGuard: Guard, onSaved: (page: DocPage) => void) {
  const [draft, setDraft] = useState(page.markdown);
  const [saved, setSaved] = useState(page);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [conflict, setConflict] = useState<DocPage>();
  const dirty = draft !== saved.markdown;
  const saveRef = useRef(false);

  useEffect(() => {
    if (!dirty && !pending) return;
    const guard = () => !pending && window.confirm('Abandonner le brouillon non enregistré ?');
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    registerGuard(guard);
    window.addEventListener('beforeunload', beforeUnload);
    return () => { registerGuard(null); window.removeEventListener('beforeunload', beforeUnload); };
  }, [dirty, pending, registerGuard]);

  useEffect(() => {
    if (!dirty || pending || error) return;
    const timer = window.setTimeout(async () => {
      if (saveRef.current) return;
      saveRef.current = true;
      setPending(true);
      try {
        const result = await api.savePage(page.id, draft, saved.revision);
        setSaved(result);
        onSaved(result);
      } catch (reason) {
        setError(message(reason));
        if (reason instanceof ApiError && reason.status === 409) {
          try { setConflict(await api.page(page.id)); } catch { /* The draft remains available. */ }
        }
      } finally {
        saveRef.current = false;
        setPending(false);
      }
    }, 450);
    return () => clearTimeout(timer);
  }, [api, dirty, draft, error, onSaved, page.id, pending, saved.revision]);

  function retry() {
    if (conflict) {
      setSaved(conflict);
      setConflict(undefined);
    }
    setError('');
  }

  return { draft, setDraft, dirty, pending, error, conflict, retry };
}

function LinkPicker({ request, pages, onClose }: { request: LinkRequest; pages: PageSummary[]; onClose: () => void }) {
  const [query, setQuery] = useState('');
  const matches = pages.filter(page => page.title.toLocaleLowerCase('fr').includes(query.trim().toLocaleLowerCase('fr')));
  const titles = new Map(pages.map(page => [page.id, page]));
  function path(page: PageSummary) {
    const parts = [page.title];
    let parent = page.parentId && titles.get(page.parentId);
    while (parent) {
      parts.unshift(parent.title);
      parent = parent.parentId && titles.get(parent.parentId);
    }
    return parts.join(' / ');
  }
  return <Dialog title="Insérer un lien interne" onClose={onClose}>
    <div className="form-body docs-link-picker">
      <label>Rechercher une page<input value={query} onChange={event => setQuery(event.target.value)} /></label>
      {matches.length ? matches.map(page => <button type="button" className="button" key={page.id} onClick={() => {
        onClose();
        requestAnimationFrame(() => request.apply({ kind: 'page', id: page.id }));
      }}>{path(page)}</button>) : <p>Aucune page correspondante.</p>}
    </div>
  </Dialog>;
}

function AttachmentForm({ request, api, pageId, close }: {
  request: AttachmentRequest; api: DocsApi; pageId: string; close: () => void;
}) {
  const identifier = useRef('');
  const image = request.kind === 'image';
  return <DocsForm title={image ? 'Insérer une image' : 'Joindre un fichier'} action="Insérer" pendingLabel="Transfert en cours…" close={close}
    submit={async values => {
      const file = values.get('file');
      if (!(file instanceof File) || !file.name) throw new Error('Sélectionnez un fichier.');
      if (file.size > 10 * 1024 * 1024) throw new Error('Ce fichier dépasse la limite de 10 Mio.');
      const alt = String(values.get('alt') ?? '').trim();
      if (image && !alt) throw new Error('Renseignez le texte alternatif de l’image.');
      identifier.current ||= crypto.randomUUID();
      const asset = await api.uploadAsset(pageId, identifier.current, file, request.kind);
      requestAnimationFrame(() => request.insert(asset.id, image ? alt : asset.name));
    }}>
    <p>{image ? 'PNG, JPEG, WebP ou GIF.' : 'PDF, PNG, JPEG, WebP ou GIF.'} 10 Mio maximum.</p>
    <label>Fichier local<input name="file" type="file" required onChange={() => { identifier.current = ''; }}
      accept={(image ? '' : 'application/pdf,') + 'image/png,image/jpeg,image/webp,image/gif'} /></label>
    {image && <label>Texte alternatif<input name="alt" required maxLength={180} /></label>}
  </DocsForm>;
}

type DocContentProps = {
  page: DocPage; api: DocsApi; pages: PageSummary[]; collections: CollectionSummary[]; openDoc: OpenDoc; openGalleryPage: OpenGalleryPage; refreshKey: number;
};

export function DocsEditor({ page, api, pages, collections, refreshKey, openDoc, openGalleryPage, registerGuard, onSaved }: DocContentProps & {
  registerGuard: Guard; onSaved: (page: DocPage) => void;
}) {
  const draft = usePageDraft(page, api, registerGuard, onSaved);
  const [source, setSource] = useState(false);
  const [unsupported, setUnsupported] = useState(false);
  const [link, setLink] = useState<LinkRequest>();
  const [attachment, setAttachment] = useState<AttachmentRequest>();
  const [embedded, setEmbedded] = useState<EmbeddedRequest>();
  const visualLink = useRef<((kind: LinkValue['kind']) => void) | null>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const titles = new Map(pages.map(item => [item.id, item.title]));

  function openLink() {
    if (!source) {
      visualLink.current?.('page');
      return;
    }
    const start = textarea.current?.selectionStart ?? draft.draft.length;
    const end = textarea.current?.selectionEnd ?? start;
    setLink({ kind: 'page', apply(value) {
      if (value.kind !== 'page') return;
      draft.setDraft(text => text.slice(0, start) + '[](/pages/' + value.id + ')' + text.slice(end));
      textarea.current?.focus();
    } });
  }
  function sourceAsset(kind: AttachmentKind) {
    const start = textarea.current?.selectionStart ?? draft.draft.length;
    const end = textarea.current?.selectionEnd ?? start;
    setAttachment({ kind, insert(id, label) {
      const link = (kind === 'image' ? '!' : '') + '[' + escapeLabel(label) + '](' + attachmentHref(id) + ')';
      draft.setDraft(text => text.slice(0, start) + link + text.slice(end));
      textarea.current?.focus();
      textarea.current?.setSelectionRange(start + link.length, start + link.length);
    } });
  }

  const status = draft.pending ? 'Enregistrement…' : draft.error ? 'Brouillon non enregistré' : draft.dirty ? 'Modifications en attente' : 'Enregistré';

  return <div className="docs-editor">
    <div className="docs-editor-controls">
      <button type="button" className="button" onClick={openLink}>Lien interne</button>
      {source && <>
        <button type="button" className="button" onClick={() => sourceAsset('file')}>Fichier</button>
        <button type="button" className="button" onClick={() => sourceAsset('image')}>Image</button>
      </>}
      <span role="status">{status}</span>
      <button type="button" className="button subtle" onClick={() => { setSource(!source); setUnsupported(false); }}>
        {source ? 'Mode visuel' : 'Markdown'}
      </button>
    </div>
    {unsupported && <p className="markdown-notice">Ce contenu utilise une syntaxe conservée en mode Markdown.</p>}
    <ErrorMessage>{draft.error}</ErrorMessage>
    {!!draft.error && !draft.pending && <div className="docs-save-recovery">
      {draft.conflict && <details><summary>Voir la version enregistrée</summary><pre>{draft.conflict.markdown}</pre></details>}
      <button className="button" onClick={draft.retry}>{draft.conflict ? 'Enregistrer mon brouillon à la place' : 'Réessayer'}</button>
    </div>}
    <EmbeddedViews.Provider value={{ api, pages, collections, refreshKey, open: openDoc, openGalleryPage, pageId: page.id }}>
      {source ? <textarea ref={textarea} className="markdown-source" aria-label="Source Markdown"
        value={draft.draft} onChange={event => draft.setDraft(event.target.value)} maxLength={100000} />
        : <Suspense fallback={<p>Chargement de l’éditeur…</p>}>
          <MarkdownVisual value={draft.draft} onChange={draft.setDraft} readOnly={false} references={titles}
            openLinks={setLink} visualLink={visualLink} openDoc={openDoc} openAttachment={setAttachment}
            openEmbedded={request => setEmbedded(() => request)} assetHref={api.assetHref}
            onUnsupported={() => { setUnsupported(true); setSource(true); }} />
        </Suspense>}
    </EmbeddedViews.Provider>
    {embedded && <EmbeddedViewPicker api={api} collections={collections} insert={embedded} close={() => setEmbedded(undefined)} />}
    {attachment && <AttachmentForm request={attachment} api={api} pageId={page.id} close={() => setAttachment(undefined)} />}
    {link && <LinkPicker request={link} pages={pages} onClose={() => setLink(undefined)} />}
  </div>;
}

export function DocsReader({ page, api, pages, collections, refreshKey, openDoc, openGalleryPage }: DocContentProps) {
  const [source, setSource] = useState(false);
  const visualLink = useRef(null);
  const titles = new Map(pages.map(item => [item.id, item.title]));
  return <div className="docs-editor">
    <EmbeddedViews.Provider value={{ api, pages, collections, refreshKey, open: openDoc, openGalleryPage, pageId: page.id }}>
      {source ? <>
        <p className="markdown-notice">Ce contenu est affiché en Markdown.</p>
        <textarea className="markdown-source" aria-label="Source Markdown" value={page.markdown} readOnly />
      </> : <Suspense fallback={<p role="status">Chargement de la page…</p>}>
        <MarkdownVisual value={page.markdown} readOnly references={titles} openDoc={openDoc} assetHref={api.assetHref}
          visualLink={visualLink} onUnsupported={() => setSource(true)} onChange={() => {}} openLinks={() => {}} />
      </Suspense>}
    </EmbeddedViews.Provider>
  </div>;
}
