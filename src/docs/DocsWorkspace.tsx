import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ArrowDown, FileText, List, MagnifyingGlass, Plus, Trash } from '@phosphor-icons/react';
import { ApiError } from '../api';
import { Dialog, ErrorMessage, message } from '../ui';
import type { Workspace } from '../types';
import { DocsEditor, DocsReader } from './DocsEditor';
import type { GalleryReturnTarget, OpenGalleryPage } from './gallery-navigation';
import { DocsAccessDialog, DocsDiscussion, DocsNotifications } from './DocsCollaboration';
import { DocsHistory, DocsTrash } from './DocsLifecycle';
import { DocsForm, FieldFields, PageFields, fieldInput, pagePath, placement } from './DocsForms';
import { Cell, CollectionViews } from './DocsCollection';
import { RelationCell, type SaveRelations } from './DocsRelations';
import { DocLink } from './DocsLink';
import { ViewForm } from './DocsViewForm';
import { TemplateManager } from './DocsTemplates';
import { SchemaDialog } from './DocsSchema';
import { docsApi, docHref, followDoc, type DocCollection, type DocNotification, type DocPage, type DocsApi, type DocsIndex, type DocView,
  type OpenDoc, type PageSummary, type PropertyValue } from './api';

type DocDialog = { kind: 'page'; page?: DocPage; parent: string | null; collection: string | null }
  | { kind: 'collection' | 'search' | 'templates' }
  | { kind: 'save-template'; pageId: string }
  | { kind: 'history'; pageId: string }
  | { kind: 'trash-page'; page: DocPage }
  | { kind: 'field' | 'schema'; collection: DocCollection }
  | { kind: 'view'; collection: DocCollection; view?: DocView }
  | { kind: 'remove-view'; collection: DocCollection; view: DocView };

function PageActions({ duplicate, busy, trash }: { duplicate: () => void; busy: boolean; trash: () => void }) {
  const details = useRef<HTMLDetailsElement>(null);
  const summary = useRef<HTMLElement>(null);
  function close() {
    if (details.current) details.current.open = false;
    summary.current?.focus();
  }
  return <details className="docs-page-actions" ref={details} onKeyDown={event => {
    if (event.key === 'Escape' && details.current?.open) { event.preventDefault(); close(); }
  }} onBlur={event => {
    if (!event.currentTarget.contains(event.relatedTarget)) event.currentTarget.open = false;
  }}>
    <summary className="button" ref={summary}>Actions de la page</summary>
    <div className="docs-page-action-list">
      <button className="button subtle" type="button" disabled={busy} onClick={() => { close(); duplicate(); }}>Dupliquer la page</button>
      <button className="button danger" type="button" onClick={() => { close(); trash(); }}>Mettre à la corbeille</button>
    </div>
  </details>;
}

function descendantCount(pages: PageSummary[], rootId: string) {
  const children = new Map<string, string[]>();
  for (const page of pages) {
    if (!page.parentId) continue;
    const siblings = children.get(page.parentId) ?? [];
    siblings.push(page.id);
    children.set(page.parentId, siblings);
  }
  const branch = [rootId];
  for (const id of branch) {
    for (const child of children.get(id) ?? []) branch.push(child);
  }
  return branch.length - 1;
}

function PageTree({ pages, active, open }: { pages: PageSummary[]; active: string; open: OpenDoc }) {
  const groups = new Map<string | null, PageSummary[]>();
  for (const page of pages) {
    const siblings = groups.get(page.parentId) ?? [];
    siblings.push(page);
    groups.set(page.parentId, siblings);
  }
  function branch(parent: string | null) {
    const children = groups.get(parent);
    if (!children?.length) return null;
    return <ul>{children.map(page => <li key={page.id}>
      <DocLink entry={page} open={open} active={page.id === active} icon="page" />
      {branch(page.id)}
    </li>)}</ul>;
  }
  return <div className="docs-tree">{branch(null)}</div>;
}

function SearchDialog({ api, pages, open, close }: { api: DocsApi; pages: PageSummary[]; open: OpenDoc; close: () => void }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Pick<PageSummary, 'id' | 'title'>[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const titles = new Map(pages.map(page => [page.id, page]));
  useEffect(() => {
    if (!query.trim()) { setResults([]); setPending(false); return; }
    const controller = new AbortController();
    setPending(true); setError('');
    const timer = window.setTimeout(() => {
      void api.search(query, controller.signal).then(found => {
        if (!controller.signal.aborted) setResults(found);
      }).catch(reason => {
        if (!controller.signal.aborted) setError(message(reason));
      }).finally(() => {
        if (!controller.signal.aborted) setPending(false);
      });
    }, 220);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [api, query]);
  return <Dialog title="Rechercher dans Docs" onClose={close}>
    <div className="form-body docs-link-picker">
      <label>Rechercher<input type="search" placeholder="Titre ou contenu" maxLength={200} value={query}
        onChange={event => setQuery(event.target.value)} /></label>
      <ErrorMessage>{error}</ErrorMessage>
      <div aria-live="polite" className="docs-link-picker">
        {pending ? <p>Recherche…</p> : !error && query.trim() && (results.length ? results.map(result => {
          const page = titles.get(result.id);
          return <DocLink key={result.id} entry={{ ...result, title: page ? pagePath(page, titles).join(' / ') : result.title }}
            open={id => { close(); open(id); }} />;
        }) : <p>Aucun résultat.</p>)}
      </div>
    </div>
  </Dialog>;
}

export function DocsWorkspace({ workspace, userId, selected, selectedView, open, sidebar, navigationOpen, toggleNavigation, registerGuard }: {
  workspace: Workspace; userId: number; selected: string; selectedView?: string; open: (id: string, viewId?: string) => boolean; sidebar: HTMLElement | null;
  navigationOpen: boolean; toggleNavigation: () => void; registerGuard: (guard: (() => boolean) | null) => void;
}) {
  const [revalidation, setRevalidation] = useState(0);
  const revalidate = useCallback(() => setRevalidation(value => value + 1), []);
  const api = useMemo(() => docsApi(workspace.id, revalidate), [workspace.id, revalidate]);
  const [index, setIndex] = useState<DocsIndex>();
  const indexRevision = useRef(0);
  const updateIndex = useCallback((update: (current: DocsIndex | undefined) => DocsIndex | undefined) => {
    indexRevision.current++;
    setIndex(update);
  }, []);
  const [snapshot, setSnapshot] = useState<{ id: string; page?: DocPage; collection?: DocCollection; pageCollection?: DocCollection }>();
  const [dialog, setDialog] = useState<DocDialog>();
  const [error, setError] = useState('');
  const [blocked, setBlocked] = useState(false);
  const [accessOpen, setAccessOpen] = useState(false);
  const [discussionOpen, setDiscussionOpen] = useState(false);
  const discussionButton = useRef<HTMLButtonElement>(null);
  const [focusComment, setFocusComment] = useState<{ pageId: string; id: string }>();
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [notifications, setNotifications] = useState<DocNotification[]>();
  const [notificationError, setNotificationError] = useState('');
  const [notificationGeneration, setNotificationGeneration] = useState(0);
  const refreshNotifications = useCallback(() => setNotificationGeneration(value => value + 1), []);
  const [resourceError, setResourceError] = useState<{ id: string; text: string }>();
  const [retry, setRetry] = useState(0);
  const [views, setViews] = useState<Record<string, string>>({});
  const [galleryReturn, setGalleryReturn] = useState<GalleryReturnTarget>();
  const [pendingGalleryFocus, setPendingGalleryFocus] = useState<GalleryReturnTarget>();
  const [galleryIndexReady, setGalleryIndexReady] = useState<{ selected: string; revalidation: number }>();
  const pendingFocus = useRef(false);
  const activeRoute = useRef(selected);
  useLayoutEffect(() => {
    activeRoute.current = selected;
    return () => { activeRoute.current = ''; };
  }, [selected]);
  const editorGuard = useRef<(() => boolean) | null>(null);
  const attachGuard = useCallback((guard: (() => boolean) | null) => {
    editorGuard.current = guard;
    registerGuard(guard);
  }, [registerGuard]);
  const mayReplace = () => !editorGuard.current || editorGuard.current();
  const [editorEpoch, setEditorEpoch] = useState(0);
  const [duplicating, setDuplicating] = useState(false);
  const [actionError, setActionError] = useState<{ id: string; text: string }>();
  const [notice, setNotice] = useState<{ id: string; text: string }>();

  useEffect(() => {
    const controller = new AbortController();
    const revision = indexRevision.current;
    void api.index(controller.signal).then(result => {
      if (controller.signal.aborted) return;
      if (revision === indexRevision.current) setIndex(result);
      else {
        setIndex(current => current && { ...current, access: result.access });
        revalidate();
      }
      if (revision === indexRevision.current) setGalleryIndexReady({ selected, revalidation });
      setError('');
      setBlocked(false);
      if (result.access === 'reader') setDialog(current => current?.kind === 'search' ? current : undefined);
      if (result.access !== 'owner') setAccessOpen(false);
    }).catch(reason => {
      if (controller.signal.aborted) return;
      if (reason instanceof ApiError && (reason.status === 404 || reason.status === 403 || reason.status === 401)) {
        api.invalidatePending();
        setBlocked(true);
        setIndex(undefined);
        setSnapshot(undefined);
        setDialog(undefined);
        setAccessOpen(false);
        setDiscussionOpen(false);
        setFocusComment(undefined);
        setNotificationsOpen(false);
        setNotifications(undefined);
        setNotificationError('');
        setResourceError(undefined);
        setActionError(undefined);
        setNotice(undefined);
        setViews({});
      } else setError(message(reason));
    });
    return () => controller.abort();
  }, [api, retry, revalidation, revalidate, selected]);

  useEffect(() => {
    function onFocus() {
      revalidate();
      refreshNotifications();
    }
    function onVisibility() {
      if (document.visibilityState === 'visible') onFocus();
    }
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [revalidate, refreshNotifications]);

  const available = !!index;
  const canEdit = !!index && index.access !== 'reader';
  const owner = index?.access === 'owner';
  useEffect(() => {
    if (!available) return;
    const controller = new AbortController();
    void api.notifications(controller.signal).then(result => {
      if (controller.signal.aborted) return;
      setNotifications(result);
      setNotificationError('');
    }).catch(reason => {
      if (controller.signal.aborted) return;
      setNotifications(undefined);
      setNotificationError(message(reason));
    });
    return () => controller.abort();
  }, [api, available, notificationGeneration]);

  function openNotification(item: DocNotification) {
    if (!open(item.pageId)) return;
    setNotificationsOpen(false);
    setDiscussionOpen(true);
    setFocusComment({ pageId: item.pageId, id: item.commentId });
    if (!item.readAt) void api.readNotification(item.commentId).then(refreshNotifications).catch(refreshNotifications);
  }

  const pageSummary = index?.pages.find(item => item.id === selected);
  const pageCollectionId = pageSummary?.collectionId;
  const isPage = !!pageSummary;
  const isCollection = !!index?.collections.some(item => item.id === selected);
  const collectionRevalidation = isCollection ? revalidation : 0;
  useEffect(() => {
    if (!isPage && !isCollection) return;
    let active = true;
    setResourceError(undefined);
    if (isPage) {
      void Promise.all([api.page(selected), pageCollectionId ? api.collection(pageCollectionId) : undefined]).then(([page, pageCollection]) => {
        if (active) setSnapshot({ id: selected, page, pageCollection });
      }).catch(reason => { if (active) { setSnapshot(undefined); setResourceError({ id: selected, text: message(reason) }); } });
    } else {
      void api.collection(selected).then(collection => {
        if (active) setSnapshot({ id: selected, collection });
      }).catch(reason => { if (active) { setSnapshot(undefined); setResourceError({ id: selected, text: message(reason) }); } });
    }
    return () => { active = false; };
  }, [api, collectionRevalidation, isCollection, isPage, pageCollectionId, selected, retry]);
  const resource = index && (isPage || isCollection) && snapshot?.id === selected ? snapshot : undefined;
  useEffect(() => {
    if (!pendingFocus.current || !resource) return;
    pendingFocus.current = false;
    document.getElementById('workspace')?.focus({ preventScroll: true });
  }, [resource]);

  useLayoutEffect(() => {
    if (!pendingGalleryFocus) return;
    const cancel = () => {
      pendingFocus.current = false;
      setPendingGalleryFocus(undefined);
    };
    document.addEventListener('keydown', cancel, true);
    document.addEventListener('pointerdown', cancel, true);
    return () => {
      document.removeEventListener('keydown', cancel, true);
      document.removeEventListener('pointerdown', cancel, true);
    };
  }, [pendingGalleryFocus]);

  useEffect(() => {
    const target = pendingGalleryFocus;
    if (!target || resource?.id !== target.destinationId || galleryIndexReady?.selected !== target.destinationId
      || galleryIndexReady.revalidation !== revalidation) return;
    const title = document.getElementById('workspace');
    if (!(title instanceof HTMLElement)) return;
    let observer: MutationObserver;
    let timeout = 0;
    let originBlock: HTMLElement | undefined;
    const cleanup = () => {
      observer.disconnect();
      window.clearTimeout(timeout);
      document.removeEventListener('keydown', stopOnInteraction, true);
      document.removeEventListener('pointerdown', stopOnInteraction, true);
      title.removeEventListener('blur', stopOnTitleBlur);
    };
    const finish = () => {
      cleanup();
      setPendingGalleryFocus(undefined);
    };
    const stopOnInteraction = () => finish();
    const stopOnTitleBlur = () => finish();
    const focusTitle = () => {
      finish();
      document.getElementById('workspace')?.focus({ preventScroll: true });
    };
    const inspect = () => {
      if (target.kind === 'collection') {
        const sourceView = resource.collection?.views.find(item => item.id === target.viewId);
        if (!sourceView || !('layout' in sourceView) || sourceView.layout !== 'gallery') {
          focusTitle();
          return;
        }
      }
      const block = target.kind === 'embedded'
        ? [...document.querySelectorAll<HTMLElement>('.docs-embedded-view')].find(element =>
          element.dataset.docEmbeddedIndex === String(target.blockIndex ?? 0)
          && element.dataset.docEmbeddedViewId === target.viewId)
        : null;
      if (target.kind === 'embedded') {
        if (originBlock && !originBlock.isConnected) { finish(); return; }
        if (block && !originBlock) originBlock = block;
        if (!block) {
          const replacement = [...document.querySelectorAll<HTMLElement>('.docs-embedded-view')]
            .some(element => element.dataset.docEmbeddedIndex === String(target.blockIndex ?? 0));
          if (replacement) finish();
          return;
        }
        if (block.dataset.docEmbeddedLayout !== 'gallery') {
          if (block.querySelector('.docs-embedded-body') && !block.querySelector('[role="status"]')) focusTitle();
          return;
        }
      }
      if (target.kind === 'collection' && selectedView !== target.viewId) return;
      const root = target.kind === 'embedded' ? block : document;
      const gallery = root?.querySelector('.docs-gallery');
      if (gallery) {
        const card = gallery.querySelector(`[data-doc-gallery-page="${target.cardPageId}"] a`);
        if (card instanceof HTMLElement) {
          finish();
          card.focus();
          card.scrollIntoView({ block: 'nearest' });
        } else focusTitle();
        return;
      }
      if (block?.querySelector('.docs-embedded-body') && !block.querySelector('[role="status"]')) focusTitle();
    };
    observer = new MutationObserver(inspect);
    document.addEventListener('keydown', stopOnInteraction, true);
    document.addEventListener('pointerdown', stopOnInteraction, true);
    title.addEventListener('blur', stopOnTitleBlur);
    timeout = window.setTimeout(focusTitle, 5000);
    observer.observe(document.body, { childList: true, subtree: true });
    inspect();
    return cleanup;
  }, [pendingGalleryFocus, resource, selectedView, galleryIndexReady, revalidation]);

  useEffect(() => {
    if (pendingGalleryFocus && selected !== pendingGalleryFocus.destinationId && selected !== pendingGalleryFocus.cardPageId) {
      setPendingGalleryFocus(undefined);
    }
  }, [pendingGalleryFocus, selected]);

  function openPage(id: string, viewId?: string) {
    if (open(id, viewId)) {
      setGalleryReturn(undefined);
      setPendingGalleryFocus(undefined);
      if (id !== selected) {
      pendingFocus.current = true;
      setFocusComment(undefined);
      }
    }
  }
  const openGalleryPage: OpenGalleryPage = (id, origin) => {
    if (!open(id)) return false;
    setPendingGalleryFocus(undefined);
    setGalleryReturn({ ...origin, cardPageId: id });
    setFocusComment(undefined);
    pendingFocus.current = id !== selected;
    return true;
  };
  function returnToGallery() {
    if (!galleryReturn || !open(galleryReturn.destinationId,
      galleryReturn.kind === 'collection' ? galleryReturn.viewId : undefined)) return;
    pendingFocus.current = true;
    setGalleryIndexReady(undefined);
    revalidate();
    setFocusComment(undefined);
    setPendingGalleryFocus(galleryReturn);
    setGalleryReturn(undefined);
  }
  function setView(collection: string, view: string) {
    if (selected === collection && selectedView) openPage(collection, view);
    setViews(current => ({ ...current, [collection]: view }));
  }
  const updateSavedPage = useCallback((saved: DocPage) => {
    setSnapshot(current => current?.id === saved.id && current.page && current.page.revision <= saved.revision
      ? { ...current, page: saved } : current);
    updateIndex(current => current && { ...current,
      pages: current.pages.map(item => item.id === saved.id ? { ...item, title: saved.title } : item),
    });
  }, [updateIndex]);

  function upsertPage(saved: DocPage) {
    const { markdown: _markdown, backlinks: _backlinks, revision: _revision, skippedTemplateProperties: _skipped, ...summary } = saved;
    updateIndex(current => current && { ...current,
      pages: [...current.pages.filter(item => item.id !== summary.id), summary]
        .sort((a, b) => a.title.localeCompare(b.title, 'fr') || a.id.localeCompare(b.id)),
    });
  }

  function replaceDocument(saved: DocPage) {
    upsertPage(saved);
    setSnapshot(current => current?.id === saved.id ? { ...current, page: saved } : current);
    if (activeRoute.current === saved.id) setEditorEpoch(value => value + 1);
  }

  async function duplicateDocument(source: DocPage) {
    if (duplicating) return;
    setDuplicating(true); setActionError(undefined);
    try {
      const copied = await api.duplicatePage(source.id);
      upsertPage(copied);
      if (activeRoute.current === source.id) openPage(copied.id);
      setNotice({ id: copied.id, text: 'Copie créée.' });
    } catch (reason) {
      setActionError({ id: source.id, text: message(reason) });
    } finally { setDuplicating(false); }
  }

  function updateCollection(collection: DocCollection) {
    setSnapshot({ id: collection.id, collection });
  }
  function applyProperty(changed: PageSummary, _field: string) {
    updateIndex(current => current && {
      ...current, pages: current.pages.map(page => {
        if (page.id !== changed.id) return page;
        return { ...page, properties: changed.properties };
      }),
    });
  }
  async function updateProperty(id: string, field: string, value: PropertyValue) {
    applyProperty(await api.saveProperty(id, field, value), field);
    revalidate();
  }
  const saveRelations: SaveRelations = async (id, field, data) => {
    applyProperty(await api.saveRelations(id, field, data), field);
    revalidate();
  };
  const close = () => setDialog(undefined);
  const pageMap = new Map(index?.pages.map(item => [item.id, item]));
  const page = resource?.page;
  const collection = resource?.collection;
  const view = collection?.views.find(item => item.id === (selectedView ?? views[collection.id])) ?? collection?.views[0];
  const currentPage = pageSummary ?? page;
  const isTrash = canEdit && selected === 'corbeille';
  const pageToTrash = canEdit && dialog?.kind === 'trash-page' && selected === dialog.page.id ? dialog.page : undefined;
  const nestedPages = pageToTrash ? descendantCount(index?.pages ?? [], pageToTrash.id) : 0;

  const navigation = index && <>
    <button className="button docs-search" onClick={() => setDialog({ kind: 'search' })}><MagnifyingGlass size={16} />Rechercher dans Docs</button>
    <section aria-label="Pages de l’espace"><div className="sidebar-section docs-side-heading"><span>PAGES</span>
      {canEdit && <button className="icon-button" aria-label="Nouvelle page" onClick={() => setDialog({ kind: 'page', parent: null, collection: null })}><Plus size={16} /></button>}</div>
      <PageTree pages={index.pages} active={selected} open={openPage} />
    </section>
    <section aria-label="Collections de l’espace"><div className="sidebar-section docs-side-heading"><span>COLLECTIONS</span>
      {canEdit && <button className="icon-button" aria-label="Nouvelle collection" onClick={() => setDialog({ kind: 'collection' })}><Plus size={16} /></button>}</div>
      {index.collections.map(item => <DocLink key={item.id} entry={item} open={openPage} active={item.id === selected} icon="collection" />)}
    </section>
    {canEdit && <><button className="button docs-search" onClick={() => setDialog({ kind: 'templates' })}>Modèles</button>
    <a className={'nav-item docs-nav-link' + (isTrash ? ' active' : '')} href={docHref('corbeille')}
      aria-current={isTrash ? 'page' : undefined} onClick={event => followDoc(event, 'corbeille', openPage)}>
      <Trash size={16} aria-hidden /><span>Corbeille</span>
    </a></>}
  </>;

  return <>
    {sidebar && navigation && createPortal(navigation, sidebar)}
    <header className="docs-topbar">
      <button className="button docs-mobile-menu" aria-label="Ouvrir la navigation Docs" aria-expanded={navigationOpen} onClick={toggleNavigation}><List size={20} /></button>
      <div className="docs-breadcrumb">{[workspace.name, 'Docs', ...(currentPage ? pagePath(currentPage, pageMap) : collection ? [collection.title] : isTrash ? ['Corbeille'] : [])].join(' / ')}</div>
      {index && <div className="docs-row docs-topbar-actions">
        <button className="button" aria-haspopup="dialog" onClick={() => { setNotificationsOpen(true); refreshNotifications(); }}>
          Notifications{notifications?.some(item => !item.readAt) && ' · non lues'}
        </button>
        {page && <button ref={discussionButton} className="button" aria-expanded={discussionOpen}
          aria-controls={discussionOpen ? 'docs-discussion' : undefined}
          onClick={() => { setFocusComment(undefined); setDiscussionOpen(value => !value); }}>Commentaires</button>}
        <a className="button" href={api.exportHref} download><ArrowDown size={16} />Exporter</a>
        {owner && <button className="button primary" aria-haspopup="dialog" onClick={() => setAccessOpen(true)}>Accès Docs</button>}
      </div>}
    </header>
    <div className={page && discussionOpen ? 'docs-with-discussion' : undefined}>
    <div className={'docs-content' + (page ? ' docs-document' : '')}>
      {blocked && <><h1 id="workspace" tabIndex={-1}>Document indisponible</h1>
        <p>Cette adresse est indisponible avec votre session.</p></>}
      {(error || resourceError?.id === selected) && <div className="docs-problem">
        <ErrorMessage>{error || resourceError?.text}</ErrorMessage>
        <button className="button" onClick={() => setRetry(value => value + 1)}>Réessayer</button>
      </div>}
      {notice?.id === selected && <p className="docs-lifecycle-notice" role="status">{notice.text}</p>}
      {actionError?.id === selected && <ErrorMessage>{actionError.text}</ErrorMessage>}
      {!index && !error && !blocked && <p role="status">Chargement des documents…</p>}
      {index && selected === 'home' && <>
        <div className="docs-heading"><div><span className="docs-heading-icon"><FileText size={23} /></span><h1 id="workspace" tabIndex={-1}>Docs</h1></div>
          {canEdit && <div className="docs-row">
            <button className="button" onClick={() => setDialog({ kind: 'collection' })}>Nouvelle collection</button>
            <button className="button primary" onClick={() => setDialog({ kind: 'page', parent: null, collection: null })}>Nouvelle page</button>
          </div>}
        </div>
        {!index.pages.length && !index.collections.length ? <p className="docs-empty">Cet espace est vide.</p> :
          <section className="docs-home-links" aria-label="Contenu de Docs">
            {index.pages.filter(item => !item.parentId).map(item => <DocLink key={item.id} entry={item} open={openPage} icon="page" />)}
            {index.collections.map(item => <DocLink key={item.id} entry={item} open={openPage} icon="collection" />)}
          </section>}
      </>}
      {index && selected !== 'home' && !isTrash && !isPage && !isCollection && <><h1 id="workspace" tabIndex={-1}>Page indisponible</h1>
        <p>Cette adresse est indisponible dans votre espace.</p></>}
      {(isPage || isCollection) && !resource && resourceError?.id !== selected && <p role="status">Chargement…</p>}
      {index && isTrash && <DocsTrash api={api} restored={result => {
        upsertPage(result.page);
        setRetry(value => value + 1);
        if (activeRoute.current === 'corbeille') openPage(result.page.id);
        setNotice({ id: result.page.id, text: result.parentUnavailable ? 'Page restaurée à la racine de Docs.'
          : result.count === 1 ? 'Page restaurée.' : result.count + ' pages restaurées.' });
      }} />}
      {page && currentPage && index && <>
        <div className="docs-heading"><div><span className="docs-heading-icon"><FileText size={23} aria-hidden /></span>
          <h1 id="workspace" tabIndex={-1}>{currentPage.title}</h1>
          {!canEdit && <span className="docs-reader-badge">Lecture seule</span>}</div>
          {galleryReturn?.cardPageId === page.id && <button className="button" onClick={returnToGallery}>
            {galleryReturn.kind === 'embedded' ? 'Retour à la vue intégrée' : 'Retour à la galerie'}
          </button>}
          {canEdit && <div className="docs-row">
            <button className="button" onClick={() => setDialog({ kind: 'save-template', pageId: page.id })}>Enregistrer comme modèle</button>
            <button className="button" onClick={() => setDialog({ kind: 'page', page: { ...page, ...currentPage }, parent: currentPage.parentId, collection: currentPage.collectionId })}>Paramètres de la page</button>
            <button className="button primary" onClick={() => setDialog({ kind: 'page', parent: page.id, collection: null })}><Plus size={16} />Sous-page</button>
            <button className="button" onClick={() => setDialog({ kind: 'history', pageId: page.id })}>Historique</button>
            <PageActions busy={duplicating} duplicate={() => void duplicateDocument(page)}
              trash={() => setDialog({ kind: 'trash-page', page })} />
          </div>}
        </div>
        {resource.pageCollection && <section className="docs-properties" aria-label="Propriétés de la page">
          <DocLink entry={resource.pageCollection} open={openPage} />
          {resource.pageCollection.fields.map(field => <div className="docs-property" key={field.id}>
            <span>{field.name}</span>{field.kind === 'relation'
              ? <RelationCell page={currentPage} field={field} pages={pageMap} open={openPage}
                target={index.collections.find(item => item.id === field.targetCollectionId)} save={canEdit ? saveRelations : undefined} />
              : <Cell page={currentPage} field={field} update={canEdit ? updateProperty : undefined} />}
          </div>)}
        </section>}
        {canEdit ? <DocsEditor key={page.id + ":" + editorEpoch} page={page} api={api} pages={index.pages} collections={index.collections} refreshKey={notificationGeneration} openDoc={openPage} openGalleryPage={openGalleryPage}
          registerGuard={attachGuard} onSaved={updateSavedPage} /> : <DocsReader key={page.id} page={page} api={api} pages={index.pages} collections={index.collections} refreshKey={notificationGeneration} openDoc={openPage} openGalleryPage={openGalleryPage} />}
        <section className="docs-backlinks"><h2>Backlinks</h2>
          {page.backlinks.length ? page.backlinks.map(id => {
            const related = pageMap.get(id);
            return related && <DocLink key={id} entry={related} open={openPage} />;
          }) : <p>Aucune page liée.</p>}
        </section>
      </>}
      {collection && view && index && <CollectionViews key={view.id} collection={collection} view={view} pages={index.pages} collections={index.collections}
        open={openPage} setView={id => setView(collection.id, id)} update={updateProperty} saveRelations={saveRelations} readOnly={!canEdit}
        newView={() => setDialog({ kind: 'view', collection })}
        editView={() => setDialog({ kind: 'view', collection, view })}
        deleteView={() => setDialog({ kind: 'remove-view', collection, view })}
        newPage={() => setDialog({ kind: 'page', parent: null, collection: collection.id })}
        schema={() => setDialog({ kind: 'schema', collection })}
        newField={() => setDialog({ kind: 'field', collection })} api={api} openGalleryPage={openGalleryPage} />}
    </div>
    {page && discussionOpen && <DocsDiscussion key={page.id} api={api} pageId={page.id} canEdit={canEdit} owner={owner}
      userId={userId} refreshKey={notificationGeneration} focusComment={focusComment?.pageId === page.id ? focusComment.id : undefined}
      close={() => { setDiscussionOpen(false); setFocusComment(undefined); discussionButton.current?.focus(); }}
      refreshNotifications={refreshNotifications} />}
    </div>
    {owner && accessOpen && <DocsAccessDialog api={api} workspace={workspace} close={() => setAccessOpen(false)} />}
    {index && notificationsOpen && <DocsNotifications items={notifications} error={notificationError}
      close={() => setNotificationsOpen(false)} open={openNotification} refresh={refreshNotifications} />}
    {canEdit && dialog?.kind === 'history' && selected === dialog.pageId && <DocsHistory pageId={dialog.pageId} api={api} close={close}
      mayReplace={mayReplace} restored={updated => {
        replaceDocument(updated);
        setNotice({ id: updated.id, text: 'Révision ' + updated.revision + ' créée.' });
      }} />}
    {pageToTrash && <DocsForm title="Mettre à la corbeille" action="Mettre à la corbeille" close={close} destructive
      submit={async () => {
        if (!mayReplace()) return false;
        const result = await api.trashPage(pageToTrash.id, pageToTrash.revision);
        setRetry(value => value + 1);
        if (activeRoute.current === pageToTrash.id) {
          attachGuard(null);
          openPage('corbeille');
        }
        setNotice({ id: 'corbeille', text: result.count === 1 ? 'Page mise à la corbeille.' : result.count + ' pages mises à la corbeille.' });
      }}>
      <p>« {pageToTrash.title} »{nestedPages ? ' et ses ' + nestedPages + (nestedPages === 1 ? ' sous-page' : ' sous-pages') : ''}
        {nestedPages ? ' disparaîtront' : ' disparaîtra'} de Docs. La restauration restera disponible.</p>
    </DocsForm>}
    {canEdit && dialog?.kind === 'templates' && index && <TemplateManager api={api} collections={index.collections} close={close} />}
    {canEdit && dialog?.kind === 'save-template' && page && page.id === dialog.pageId &&
      <DocsForm title="Enregistrer comme modèle" action="Enregistrer" close={close} submit={async values => {
        if (editorGuard.current) throw new Error('Attendez que le contenu de la page soit enregistré avant de créer le modèle.');
        await api.saveTemplate(page.id, String(values.get('name')), page.revision);
        setNotice({ id: page.id, text: 'Modèle enregistré.' });
      }}>
        <p>{resource.pageCollection ? 'Ce modèle sera disponible dans la collection « ' + resource.pageCollection.title + ' » avec les propriétés copiées.'
          : 'Ce modèle sera disponible dans tout l’espace.'}</p>
        <label>Nom du modèle<input name="name" defaultValue={page.title} maxLength={160} required /></label>
      </DocsForm>}
    {dialog?.kind === 'search' && <SearchDialog api={api} pages={index?.pages ?? []} open={openPage} close={close} />}
    {canEdit && dialog?.kind === 'page' && index && <DocsForm title={dialog.page ? 'Paramètres de la page' : dialog.parent ? 'Nouvelle sous-page' : 'Nouvelle page'}
      action={dialog.page ? 'Enregistrer' : 'Créer la page'} close={close} submit={async values => {
        const data = placement(values);
        if (dialog.page) {
          if (!mayReplace()) return false;
          replaceDocument(await api.placePage(dialog.page.id, data, dialog.page.revision));
        } else {
          const created = await api.createPage(data, String(values.get('template') || '') || null);
          if (created.skippedTemplateProperties) {
            setNotice({ id: created.id, text: 'Les propriétés du modèle devenues incompatibles ont été laissées vides.' });
          }
          upsertPage(created);
          openPage(created.id);
        }
      }}><PageFields api={api} page={dialog.page} parents={index.pages} collections={index.collections} parentId={dialog.parent} collectionId={dialog.collection} /></DocsForm>}
    {canEdit && dialog?.kind === 'collection' && <DocsForm title="Nouvelle collection" action="Créer la collection" close={close} submit={async data => {
      const created = await api.createCollection({ title: String(data.get('title')), description: String(data.get('description')) });
      updateIndex(current => current && { ...current, collections: [...current.collections,
        { id: created.id, title: created.title, description: created.description },
      ].sort((a, b) => a.title.localeCompare(b.title, 'fr') || a.id.localeCompare(b.id)) });
      openPage(created.id);
    }}><label>Titre<input name="title" required maxLength={160} /></label>
      <label>Description<textarea name="description" maxLength={1000} rows={3} /></label></DocsForm>}
    {canEdit && dialog?.kind === 'field' && index && <DocsForm title="Nouvelle propriété" action="Ajouter la propriété" close={close} submit={async data => {
      const field = await api.createField(dialog.collection.id, fieldInput(data, dialog.collection.fields));
      updateCollection({ ...dialog.collection, fields: [...dialog.collection.fields, field] });
      if (field.kind === 'aggregate' || field.kind === 'formula') revalidate();
    }}><FieldFields collections={index.collections} collection={dialog.collection} api={api} /></DocsForm>}
    {canEdit && dialog?.kind === 'schema' && index && collection?.id === dialog.collection.id && <SchemaDialog collection={collection} collections={index.collections} api={api} close={close}
      changed={(fields, refresh) => {
        updateCollection({ ...collection, fields });
        if (refresh) {
          setRetry(value => value + 1);
          revalidate();
        }
      }} />}
    {canEdit && dialog?.kind === 'view' && <ViewForm collection={dialog.collection} view={dialog.view} close={close} save={async data => {
      const old = dialog.view;
      const saved = await api.saveView(dialog.collection.id, old?.id ?? null, data);
      const existing = dialog.collection.views;
      updateCollection({ ...dialog.collection, views: old ? existing.map(item => item.id === old.id ? saved : item) : [...existing, saved] });
      setView(dialog.collection.id, saved.id);
    }} />}
    {canEdit && dialog?.kind === 'remove-view' && <DocsForm title="Supprimer la vue" action="Supprimer la vue" close={close} submit={async () => {
      await api.deleteView(dialog.collection.id, dialog.view.id);
      updateCollection({ ...dialog.collection, views: dialog.collection.views.filter(item => item.id !== dialog.view.id) });
    }}><p>Supprimer « {dialog.view.name} » ? Les pages et leurs propriétés sont conservées.</p></DocsForm>}
  </>;
}
