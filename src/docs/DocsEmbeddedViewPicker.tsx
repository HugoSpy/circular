import { createContext, useState } from 'react';
import { ErrorMessage, message } from '../ui';
import { DocsForm } from './DocsForms';
import { useCollection } from './useCollection';
import type { OpenGalleryPage } from './gallery-navigation';
import { escapeLabel, type CollectionSummary, type DocsApi,
  type EmbeddedRequest, type OpenDoc, type PageSummary } from './api';

export type EmbeddedContext = {
  api: DocsApi; pages: PageSummary[]; collections: CollectionSummary[]; open: OpenDoc; openGalleryPage: OpenGalleryPage;
  pageId: string; refreshKey: number;
};
export const EmbeddedViews = createContext<EmbeddedContext | undefined>(undefined);

export function EmbeddedViewPicker({ api, collections, insert, close }: {
  api: DocsApi; collections: CollectionSummary[]; insert: EmbeddedRequest; close: () => void;
}) {
  const [collectionId, setCollection] = useState('');
  const [viewId, setView] = useState('');
  const [refresh, setRefresh] = useState(0);
  const result = useCollection(api, collectionId || undefined, refresh);
  const view = result?.collection?.views.find(item => item.id === viewId);
  return <DocsForm title="Insérer une vue de collection" action="Insérer la vue" close={close} submit={async () => {
    if (!result?.collection || !view) return false;
    const label = escapeLabel(result.collection.title + ' — ' + view.name);
    requestAnimationFrame(() => insert({ collectionId, viewId, label }));
  }}>
    <label>Collection<select aria-label="Collection" value={collectionId} required onChange={event => {
      setCollection(event.target.value);
      setView('');
    }}><option value="">Choisir une collection</option>
      {collections.map(collection => <option key={collection.id} value={collection.id}>{collection.title}</option>)}
    </select></label>
    {!collections.length && <p>Aucune collection disponible.</p>}
    {collectionId && !result && <p role="status">Chargement des vues…</p>}
    {result?.error != null && <><ErrorMessage>{message(result.error)}</ErrorMessage>
      <button className="button" type="button" onClick={() => setRefresh(value => value + 1)}>Réessayer</button></>}
    {result?.collection && <label>Vue enregistrée<select aria-label="Vue enregistrée" value={viewId} required
      onChange={event => setView(event.target.value)}>
      <option value="">Choisir une vue</option>
      {result.collection.views.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
    </select></label>}
  </DocsForm>;
}
