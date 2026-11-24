import type { MouseEvent } from 'react';
import { ApiError, request } from '../api';

export type ScalarValue = string | number | boolean | null;
export type PropertyValue = ScalarValue | string[];
export type CalculationError = { error: 'out_of_range' | 'division_by_zero' };
export type AggregateError = CalculationError;
export type PropertyKind = 'text' | 'number' | 'date' | 'select' | 'checkbox' | 'url' | 'multi' | 'relation' | 'aggregate' | 'formula';
export type Aggregation = { relationFieldId: string; operation: 'count' | 'sum' | 'average'; sourceFieldId?: string };
export type Formula = { expression: string; dependencies?: string[] };
export type PropertyField = { id: string; name: string; kind: PropertyKind; options: string[]; targetCollectionId?: string; aggregation?: Aggregation; formula?: Formula };
export type RelationUpdate = { add: string[]; remove: string[] };
export type Placement = { title: string; parentId: string | null; collectionId: string | null };
export type PageSummary = Placement & { id: string; properties: Record<string, PropertyValue | AggregateError> };
export type DocPage = PageSummary & { markdown: string; revision: number; backlinks: string[]; skippedTemplateProperties?: number };
export const attachmentHref = (id: string) => '/attachments/' + id;
export const escapeLabel = (text: string) => text.replace(/[\\`*_{}\[\]()<>#+.!|~&-]/g, '\\$&');

export type AttachmentKind = 'file' | 'image';
export type AttachmentRequest = { kind: AttachmentKind; insert: (id: string, label: string) => void };
export type DocTemplate = { id: string; name: string; collectionId: string | null };
export type RevisionSummary = { revision: number; title: string; author: string | null; createdAt: string | null };
export type DocRevision = RevisionSummary & { markdown: string };
export type TrashEntry = {
  id: string; rootId: string; title: string; parentId: string | null;
  parentTitle: string | null; parentAvailable: boolean; trashedAt: string; count: number;
};
export type TrashRestore = { page: DocPage; count: number; parentUnavailable: boolean };
export type CollectionSummary = { id: string; title: string; description: string };
export type FilterOperator = 'eq' | 'contains' | 'gte' | 'lte' | 'empty' | 'filled';
export type FilterRule = { fieldId: string; operator: FilterOperator; value: ScalarValue };
export type FilterGroup = { mode: 'all' | 'any'; conditions: FilterRule[] };
export type FilterTree = { mode: 'all' | 'any'; conditions: (FilterRule | FilterGroup)[] };
export type Layout = 'table' | 'list' | 'board' | 'calendar' | 'timeline' | 'gallery';
export type SortRule = { fieldId: string; direction: 'asc' | 'desc' };
export type ViewInput = { name: string; layout: Layout; groupBy: string | null; dateFieldId: string | null; endDateFieldId?: string | null; filterTree: FilterTree; sorts: SortRule[]; hidden: string[] };
type LegacyView = { name: string; filters: { fieldId: string; value: ScalarValue }[]; sortBy: string; direction: 'asc'|'desc'; hidden: string[] };
export type DocView = (ViewInput | LegacyView) & { id: string };
export type DocCollection = CollectionSummary & { fields: PropertyField[]; views: DocView[] };
export type GalleryPreview = { status: 'available'; assetId: string; alt: string } | { status: 'unavailable'; alt: string };
export type DocsAccess = 'owner' | 'editor' | 'reader';
export type DocsIndex = { pages: PageSummary[]; collections: CollectionSummary[]; access: DocsAccess };
export type DocPerson = { id: number; name: string };
export type DocsMember = DocPerson & { role: DocsAccess };
export type DocComment = {
  id: string; authorId: number; author: string; body: string; revision: number; createdAt: string;
  mentionId: number | null; mentionName: string | null;
};
export type DocNotification = { commentId: string; pageId: string; title: string; author: string; readAt: string | null };
export type DocCommentInput = { body: string; mentionId: number | null };
export type OpenDoc = (id: string, viewId?: string) => void;
export type EmbeddedReference = { collectionId: string; viewId: string; label: string };
export type EmbeddedRequest = (reference: EmbeddedReference) => void;
export const viewReferenceHref = (collectionId: string, viewId: string) => '/collections/' + collectionId + '/views/' + viewId;
export type LinkValue = { kind: 'page'; id: string } | { kind: 'url'; url: string; label: string };
export type LinkRequest = { kind: LinkValue['kind']; apply: (link: LinkValue) => void };

export const propertyNames: Record<PropertyKind, string> = {
  text: 'Texte', number: 'Nombre', date: 'Date', select: 'Sélection', checkbox: 'Case à cocher', url: 'URL', multi: 'Sélection multiple',
  relation: 'Relation', aggregate: 'Agrégation', formula: 'Formule',
};
export const calculationErrors: Record<CalculationError['error'], string> = {
  out_of_range: 'Résultat hors plage', division_by_zero: 'Division par zéro',
};
export const aggregationNames: Record<Aggregation['operation'], string> = {
  count: 'Nombre de pages liées', sum: 'Somme', average: 'Moyenne',
};

export function docHref(id?: string, viewId?: string) {
  const url = new URL(location.href);
  url.searchParams.delete('issue');
  url.searchParams.delete('mode');
  if (id) url.searchParams.set('docs', id);
  else url.searchParams.delete('docs');
  if (id && viewId) url.searchParams.set('docView', viewId);
  else url.searchParams.delete('docView');
  return url.pathname + url.search + url.hash;
}

export function followDoc(event: MouseEvent<HTMLAnchorElement>, id: string, open: OpenDoc, viewId?: string) {
  if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  open(id, viewId);
}

export function docsApi(workspaceId: number, revalidate: () => void) {
  const base = '/workspaces/' + workspaceId + '/docs';
  let generation = 0;
  async function sendRequest<T>(path: string, options: RequestInit) {
    const requested = generation;
    try {
      const result = await request<T>(base + path, options, workspaceId);
      if (requested !== generation) throw new ApiError('L’accès aux documents a changé.', 409);
      return result;
    } catch (reason) {
      if (path && requested === generation && !options.signal?.aborted && reason instanceof ApiError &&
          (reason.status === 403 || reason.status === 404)) revalidate();
      throw reason;
    }
  }
  const send = <T>(path: string, method: string, data?: object, signal?: AbortSignal) =>
    sendRequest<T>(path, { method, signal, body: data === undefined ? undefined : JSON.stringify(data) });
  return {
    invalidatePending: () => { generation++; },
    index: (signal: AbortSignal) => send<DocsIndex>('', 'GET', undefined, signal),
    search: (query: string, signal: AbortSignal) => send<Pick<PageSummary, 'id' | 'title'>[]>(
      '/search?' + new URLSearchParams({ q: query }), 'GET', undefined, signal,
    ),
    accessMembers: () => send<DocsMember[]>('/access', 'GET'),
    changeAccess: (id: number, role: 'editor' | 'reader') => send<void>('/access/' + id, 'PATCH', { role }),
    comments: (page: string, signal?: AbortSignal) =>
      send<{ items: DocComment[]; people: DocPerson[] }>('/pages/' + page + '/comments', 'GET', undefined, signal),
    createComment: (page: string, id: string, data: DocCommentInput) =>
      send<DocComment>('/pages/' + page + '/comments/' + id, 'PUT', data),
    editComment: (page: string, id: string, data: DocCommentInput & { revision: number }) =>
      send<DocComment>('/pages/' + page + '/comments/' + id, 'PATCH', data),
    deleteComment: (page: string, id: string) => send<void>('/pages/' + page + '/comments/' + id, 'DELETE'),
    notifications: (signal: AbortSignal) => send<DocNotification[]>('/notifications', 'GET', undefined, signal),
    readNotification: (id: string) => send<void>('/notifications/' + id + '/read', 'PATCH', {}),
    page: (id: string) => send<DocPage>('/pages/' + encodeURIComponent(id), 'GET'),
    collection: (id: string, signal?: AbortSignal) => send<DocCollection>('/collections/' + encodeURIComponent(id), 'GET', undefined, signal),
    galleryPreviews: (collectionId: string, pageIds: string[], signal?: AbortSignal) =>
      send<Record<string, GalleryPreview>>('/collections/' + encodeURIComponent(collectionId) + '/gallery-previews', 'POST', { pageIds }, signal),
    createPage: (data: Placement, templateId: string | null = null) => send<DocPage>('/pages', 'POST', { ...data, templateId }),
    templates: () => send<DocTemplate[]>('/templates', 'GET'),
    saveTemplate: (pageId: string, name: string, revision: number) =>
      send<DocTemplate>('/pages/' + pageId + '/templates', 'POST', { name, revision }),
    renameTemplate: (id: string, name: string) => send<DocTemplate>('/templates/' + id, 'PATCH', { name }),
    archiveTemplate: (id: string) => send<void>('/templates/' + id, 'DELETE'),
    placePage: (id: string, data: Placement, revision: number) =>
      send<DocPage>('/pages/' + id + '/placement', 'PATCH', { ...data, revision }),
    duplicatePage: (id: string) => send<DocPage>('/pages/' + id + '/duplicate', 'POST', {}),
    revisions: (id: string, before?: number) => send<{ items: RevisionSummary[]; nextBefore: number | null }>(
      '/pages/' + id + '/revisions' + (before ? '?before=' + before : ''), 'GET',
    ),
    revision: (id: string, version: number) => send<DocRevision>('/pages/' + id + '/revisions/' + version, 'GET'),
    restoreRevision: (id: string, version: number, revision: number) =>
      send<DocPage>('/pages/' + id + '/revisions/' + version + '/restore', 'POST', { revision }),
    trashPage: (id: string, revision: number) => send<{ id: string; count: number }>('/pages/' + id + '/trash', 'POST', { revision }),
    trash: () => send<TrashEntry[]>('/trash', 'GET'),
    restoreTrash: (id: string) => send<TrashRestore>('/trash/' + id + '/restore', 'POST', {}),
    savePage: (id: string, markdown: string, revision: number) =>
      send<DocPage>('/pages/' + id + '/body', 'PATCH', { markdown, revision }),
    saveProperty: (page: string, field: string, value: PropertyValue) =>
      send<PageSummary>('/pages/' + page + '/properties/' + field, 'PATCH', { value }),
    saveRelations: (page: string, field: string, data: RelationUpdate) =>
      send<PageSummary>('/pages/' + page + '/relations/' + field, 'PATCH', data),
    createCollection: (data: Pick<CollectionSummary, 'title' | 'description'>) =>
      send<DocCollection>('/collections', 'POST', data),
    createField: (id: string, data: Omit<PropertyField, 'id'>) =>
      send<PropertyField>('/collections/' + id + '/fields', 'POST', data),
    editField: (id: string, field: string, data: { name: string; previousOptions: string[]; options: string[]; formula?: Pick<Formula, 'expression'> }) =>
      send<PropertyField>('/collections/' + id + '/fields/' + field, 'PATCH', data),
    orderFields: (id: string, fieldIds: string[]) =>
      send<PropertyField[]>('/collections/' + id + '/fields/order', 'PATCH', { fieldIds }),
    saveView: (collection: string, view: string | null, data: ViewInput) =>
      send<DocView>('/collections/' + collection + '/views' + (view ? '/' + view : ''), view ? 'PATCH' : 'POST', data),
    deleteView: (collection: string, view: string) =>
      send<void>('/collections/' + collection + '/views/' + view, 'DELETE'),
    uploadAsset: (pageId: string, id: string, file: File, kind: AttachmentKind) =>
      sendRequest<{ id: string; name: string }>('/pages/' + pageId + '/attachments?' + new URLSearchParams({
        assetId: id, name: file.name, image: String(kind === 'image'),
      }), { method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: file }),
    assetHref: (id: string, preview = false) => '/api' + base + '/attachments/' + encodeURIComponent(id) + (preview ? '?preview=true' : ''),
    exportHref: '/api' + base + '/export',
  };
}

export type DocsApi = ReturnType<typeof docsApi>;
