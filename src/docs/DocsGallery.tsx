import { useEffect, useState } from 'react';
import { DocLink } from './DocsLink';
import { RelationLinks } from './DocsRelations';
import { isAggregateError, valueLabel } from './collection-views';
import type { CollectionSummary, DocsApi, OpenDoc, PageSummary, PropertyField } from './api';
import type { GalleryOrigin, OpenGalleryPage } from './gallery-navigation';

type Preview = { status: 'available'; assetId: string; alt: string } | { status: 'unavailable'; alt: string };

function PreviewFrame({ preview, api }: { preview: Preview | null | undefined; api: DocsApi }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [preview]);
  return <div className="docs-gallery-preview">
    {preview === undefined ? <span className="docs-gallery-placeholder">Chargement de l’aperçu…</span>
      : preview === null ? <span className="docs-gallery-placeholder">Sans image</span>
        : preview.status === 'unavailable' || failed
          ? <span className="docs-gallery-placeholder" role="img" aria-label="Image indisponible">Image indisponible</span>
          : <img src={api.assetHref(preview.assetId, true)} alt={preview.alt} loading="lazy" referrerPolicy="no-referrer"
            onError={() => setFailed(true)} />}
  </div>;
}

function CardProperty({ page, field, pageMap, collections, open }: {
  page: PageSummary; field: PropertyField; pageMap: Map<string, PageSummary>; collections: CollectionSummary[]; open: OpenDoc;
}) {
  const value = page.properties[field.id] ?? null;
  const rendered = field.kind === 'relation'
    ? <RelationLinks page={page} field={field} pages={pageMap}
      target={collections.find(item => item.id === field.targetCollectionId)} open={open} />
    : field.kind === 'url' && typeof value === 'string' && /^https?:\/\//i.test(value)
      ? <a href={value} target="_blank" rel="noreferrer">{value}</a>
      : <span className={isAggregateError(value) ? 'docs-aggregate-error' : undefined}>{valueLabel(value) || '—'}</span>;
  return <div className="docs-gallery-property"><dt>{field.name}</dt><dd>{rendered}</dd></div>;
}

export function DocsGallery({ collectionId, rows, fields, pages, collections, api, empty, openGalleryPage, origin }: {
  collectionId: string; rows: PageSummary[]; fields: PropertyField[]; pages: PageSummary[]; collections: CollectionSummary[];
  api: DocsApi; empty: string; openGalleryPage: OpenGalleryPage; origin: GalleryOrigin;
}) {
  const rowIds = rows.map(page => page.id);
  const key = rowIds.join(',');
  const [previews, setPreviews] = useState<Record<string, Preview | null>>({});
  useEffect(() => {
    const controller = new AbortController();
    setPreviews({});
    async function load() {
      const next: Record<string, Preview | null> = {};
      for (let offset = 0; offset < rowIds.length; offset += 100) {
        const batch = rowIds.slice(offset, offset + 100);
        try {
          const result = await api.galleryPreviews(collectionId, batch, controller.signal);
          for (const id of batch) next[id] = result[id] ?? null;
        } catch {
          if (controller.signal.aborted) return;
          for (const id of batch) next[id] = { status: 'unavailable', alt: '' };
        }
        if (!controller.signal.aborted) setPreviews(current => ({ ...current, ...Object.fromEntries(batch.map(id => [id, next[id]])) }));
      }
    }
    if (rowIds.length) void load();
    return () => controller.abort();
  }, [collectionId, key, pages, api]);
  const pageMap = new Map(pages.map(page => [page.id, page]));
  return <section className="docs-gallery" aria-label="Galerie des pages">
    <ul>
      {rows.map(page => <li key={page.id} data-doc-gallery-page={page.id}>
        <article className="docs-gallery-card">
          <PreviewFrame preview={previews[page.id]} api={api} />
          <div className="docs-gallery-card-body">
            <h2><DocLink entry={page} open={id => { openGalleryPage(id, origin); }} /></h2>
            {!!fields.length && <dl>{fields.map(field => <CardProperty key={field.id} page={page} field={field}
              pageMap={pageMap} collections={collections} open={open} />)}</dl>}
          </div>
        </article>
      </li>)}
    </ul>
    {!rows.length && <p className="docs-view-empty">{empty}</p>}
  </section>;
}
