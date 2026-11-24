import { useRef, useState, type FormEvent, type ReactNode } from 'react';
import { Dialog, ErrorMessage, message } from '../ui';
import { useTemplates } from './useTemplates';
import { aggregationNames, type Aggregation, type DocCollection, type DocsApi, type CollectionSummary, propertyNames, type PageSummary, type Placement, type PropertyField, type PropertyKind, type PropertyValue } from './api';
import { useCollection } from './useCollection';

export function DocsForm({ title, action, children, close, submit, destructive = false, pendingLabel = 'Enregistrement…' }: {
  title: string; action: string; pendingLabel?: string; children?: ReactNode; destructive?: boolean; close: () => void; submit: (data: FormData) => Promise<void | boolean>;
}) {
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  const form = useRef<HTMLFormElement>(null);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setPending(true); setError('');
    try {
      if (await submit(new FormData(event.currentTarget)) !== false) close();
    } catch (reason) { setError(message(reason)); }
    finally { setPending(false); }
  }
  return <Dialog title={title} pending={pending} onClose={close} onSave={() => form.current?.requestSubmit()}>
    <form ref={form} onSubmit={event => void save(event)}>
      <div className="form-body">{children}<ErrorMessage>{error}</ErrorMessage></div>
      <div className="dialog-footer">
        <button className="button" type="button" disabled={pending} onClick={close}>Annuler</button>
        <button className={destructive ? "button danger" : "button primary"} type="submit" disabled={pending}>{pending ? pendingLabel : action}</button>
      </div>
    </form>
  </Dialog>;
}

export function placement(data: FormData): Placement {
  return { title: String(data.get('title')), parentId: String(data.get('parent') || '') || null,
    collectionId: String(data.get('collection') || '') || null };
}

export function pagePath(page: PageSummary, pages: ReadonlyMap<string, PageSummary>) {
  const parts = [page.title];
  const visited = new Set([page.id]);
  let parent = page.parentId;
  while (parent && !visited.has(parent)) {
    visited.add(parent);
    const ancestor = pages.get(parent);
    if (!ancestor) break;
    parts.unshift(ancestor.title);
    parent = ancestor.parentId;
  }
  return parts;
}

export function PageFields({ page, parents, collections, parentId, collectionId, api }: {
  page?: PageSummary; parents: PageSummary[]; collections: { id: string; title: string }[];
  parentId: string | null; collectionId: string | null; api: DocsApi;
}) {
  const [collection, setCollection] = useState(collectionId ?? '');
  const lookup = new Map(parents.map(item => [item.id, item]));
  const candidates = parents.filter(item => {
    let current: PageSummary | undefined = item;
    while (current) {
      if (current.id === page?.id) return false;
      current = current.parentId ? lookup.get(current.parentId) : undefined;
    }
    return true;
  });
  return <>
    <label>Titre<input name="title" required maxLength={160} defaultValue={page?.title} /></label>
    <label>Page parente<select name="parent" aria-label="Page parente" defaultValue={parentId ?? ''}>
      <option value="">Racine de Docs</option>
      {candidates.map(item => <option value={item.id} key={item.id}>{pagePath(item, lookup).join(' / ')}</option>)}
    </select></label>
    {collectionId ? <input name="collection" type="hidden" value={collectionId} /> :
      <label>Collection<select name="collection" aria-label="Collection" value={collection} onChange={event => setCollection(event.target.value)}>
        <option value="">Aucune collection</option>
        {collections.map(collection => <option key={collection.id} value={collection.id}>{collection.title}</option>)}
      </select></label>}
    {!page && <TemplateField api={api} collection={collection} />}
  </>;
}

function TemplateField({ api, collection }: { api: DocsApi; collection: string }) {
  const templates = useTemplates(api);
  return <>
    <label>Départ<select name="template" key={collection} aria-label="Départ" defaultValue="">
      <option value="">Page vierge</option>
      {templates.items.filter(item => !item.collectionId || item.collectionId === collection)
        .map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
    </select></label>
    {templates.loading && <small>Chargement des modèles…</small>}
    <ErrorMessage>{templates.error}</ErrorMessage>
    {templates.error && <button className="button" type="button" onClick={templates.reload}>Réessayer</button>}
  </>;
}

export function formulaInput(source: string, fields: PropertyField[]) {
  const byName = new Map(fields.map(field => [field.name.toLocaleLowerCase('fr'), field.id]));
  return source.replace(/«((?:\\[\s\S]|[^»\\])+)»/g, (reference, escapedName: string) => {
    const name = escapedName.replace(/\\([\s\S])/g, '$1');
    const identifier = byName.get(name.toLocaleLowerCase('fr'));
    if (!identifier) throw new Error('Choisissez une propriété disponible dans la liste.');
    return '{' + identifier + '}';
  });
}

function formulaReference(name: string) {
  return '«' + name.replace(/\\/g, '\\\\').replace(/»/g, '\\»') + '»';
}

export function fieldInput(data: FormData, collectionFields: PropertyField[] = []): Omit<PropertyField, 'id'> {
  const kind = String(data.get('kind')) as PropertyKind;
  const options = kind === 'select' || kind === 'multi' ? String(data.get('options')).split(',').map(item => item.trim()).filter(Boolean) : [];
  const targetCollectionId = String(data.get('targetCollection') ?? '');
  const result = { name: String(data.get('name')), kind, options, ...(targetCollectionId && { targetCollectionId }) };
  if (kind === 'formula') return {
    ...result, formula: { expression: formulaInput(String(data.get('formula') ?? ''), collectionFields) },
  };
  if (kind !== 'aggregate') return result;
  const operation = String(data.get('operation')) as Aggregation['operation'];
  const relationFieldId = String(data.get('relationField') ?? '');
  const sourceFieldId = String(data.get('sourceField') ?? '');
  return { ...result, aggregation: { operation, relationFieldId, ...(sourceFieldId && { sourceFieldId }) } };
}

export function FieldFields({ collections, collection, api }: { collections: CollectionSummary[]; collection: DocCollection; api: DocsApi }) {
  const [kind, setKind] = useState<PropertyKind>('text');
  const targets = collections.filter(item => item.id !== collection.id);
  return <>
    <label>Nom<input name="name" required maxLength={160} /></label>
    <label>Type<select name="kind" aria-label="Type" value={kind} onChange={event => setKind(event.target.value as PropertyKind)}>
      {Object.entries(propertyNames).map(([key, text]) => <option key={key} value={key}
        disabled={key === 'relation' && !targets.length}>{text}</option>)}
    </select></label>
    {(kind === 'select' || kind === 'multi') && <label>Options séparées par des virgules<input name="options" required maxLength={1000} /></label>}
    {kind === 'relation' && <label>Collection cible<select name="targetCollection" aria-label="Collection cible" required defaultValue="">
      <option value="">Choisir une collection</option>
      {targets.map(collection => <option key={collection.id} value={collection.id}>{collection.title}</option>)}
    </select><small>Les pages proposées proviennent de cette collection.</small></label>}
    {kind === 'aggregate' && <AggregationFields api={api} collection={collection} collections={collections} />}
    {kind === 'formula' && <FormulaFields collection={collection} />}
  </>;
}

export function FormulaFields({ collection, initial = '' }: { collection: DocCollection; initial?: string }) {
  const input = useRef<HTMLTextAreaElement>(null);
  const references = collection.fields.filter(field => ['number', 'aggregate', 'formula'].includes(field.kind));
  const initialLabel = initial.replace(/\{([0-9a-f-]{36})\}/gi, (reference, identifier: string) => {
    const field = collection.fields.find(item => item.id === identifier.toLowerCase());
    return field ? formulaReference(field.name) : reference;
  });
  function insert(identifier: string) {
    const area = input.current;
    if (!area) return;
    const start = area.selectionStart;
    const field = references.find(item => item.id === identifier);
    if (!field) return;
    area.setRangeText(formulaReference(field.name), start, area.selectionEnd, 'end');
    area.focus();
  }
  return <fieldset className="docs-view-settings"><legend>Expression</legend>
    <label>Formule<textarea ref={input} aria-label="Formule" name="formula" defaultValue={initialLabel} required maxLength={1000}
      rows={3} spellCheck={false} /></label>
    <p>Opérateurs + − × ÷ et parenthèses. Une référence vide propage une valeur vide.</p>
    <div className="docs-row" aria-label="Propriétés disponibles" role="group">
      {references.map(field => <button type="button" className="button subtle" key={field.id}
        onClick={() => insert(field.id)}>{field.name}</button>)}
      {!references.length && <small>Ajoutez une propriété Nombre ou Agrégation.</small>}
    </div>
  </fieldset>;
}

function AggregationFields({ api, collection, collections }: { api: DocsApi; collection: DocCollection; collections: CollectionSummary[] }) {
  const [relationId, setRelation] = useState('');
  const [operation, setOperation] = useState('');
  const [retry, setRetry] = useState(0);
  const relations = collection.fields.filter(field => field.kind === 'relation');
  const relation = relations.find(field => field.id === relationId);
  const usesNumber = operation === 'sum' || operation === 'average';
  const loaded = useCollection(api, usesNumber ? relation?.targetCollectionId : undefined, retry);
  const numbers = loaded?.collection?.fields.filter(field => field.kind === 'number') ?? [];
  return <fieldset className="docs-view-settings"><legend>Calcul de l’agrégation</legend>
    <label>Relation<select name="relationField" aria-label="Relation" required value={relationId}
      onChange={event => setRelation(event.target.value)}>
      <option value="">Choisir une relation</option>
      {relations.map(field => <option key={field.id} value={field.id}>{field.name}
        {' → ' + (collections.find(item => item.id === field.targetCollectionId)?.title ?? 'Collection indisponible')}</option>)}
    </select></label>
    {!relations.length && <small>Ajoutez d’abord une propriété Relation à cette collection.</small>}
    <label>Calcul<select name="operation" aria-label="Calcul" required disabled={!relation} value={operation}
      onChange={event => setOperation(event.target.value)}>
      <option value="">Choisir un calcul</option>
      {Object.entries(aggregationNames).map(([key, name]) => <option key={key} value={key}>{name}</option>)}
    </select></label>
    {relation && usesNumber && <>
      <label>Propriété source<select name="sourceField" aria-label="Propriété source" key={relation.id} required defaultValue="">
        <option value="">Choisir une propriété Nombre</option>
        {numbers.map(field => <option key={field.id} value={field.id}>{field.name}</option>)}
      </select></label>
      {!loaded && <small role="status">Chargement des propriétés…</small>}
      {loaded?.collection && !numbers.length && <small>La collection liée ne contient aucune propriété Nombre.</small>}
      {loaded?.error != null && <><ErrorMessage>{message(loaded.error)}</ErrorMessage>
        <button type="button" className="button" onClick={() => setRetry(value => value + 1)}>Réessayer</button></>}
    </>}
  </fieldset>;
}

export function ValueInput({ field, value, setValue, label, disabled, onBlur, filter = false }: {
  field: PropertyField; value: PropertyValue; setValue: (value: PropertyValue) => void;
  label: string; disabled?: boolean; onBlur?: () => void; filter?: boolean;
}) {
  const props = { 'aria-label': label, disabled };
  if (field.kind === 'checkbox') {
    if (!filter) return <input {...props} type="checkbox" checked={value === true} onChange={event => setValue(event.target.checked)} />;
    return <select {...props} value={value === null ? '' : String(value)} onChange={event =>
      setValue(event.target.value === '' ? null : event.target.value === 'true')}>
      <option value="">Vide</option><option value="true">Cochée</option><option value="false">Décochée</option>
    </select>;
  }
  if (field.kind === 'select' || field.kind === 'multi') return <select {...props} value={String(value ?? '')}
    onChange={event => setValue(event.target.value || null)}>
    <option value="">—</option>{field.options.map(option => <option key={option}>{option}</option>)}
  </select>;
  const numeric = field.kind === 'number' || field.kind === 'aggregate' || field.kind === 'formula';
  return <input {...props} type={numeric ? 'number' : field.kind} value={String(value ?? '')} maxLength={field.kind === 'url' ? 2048 : 1000} step={numeric ? 'any' : undefined}
    required={(field.kind === 'aggregate' || field.kind === 'formula') && filter}
    onBlur={onBlur} onKeyDown={event => { if (event.key === 'Enter' && onBlur) { event.preventDefault(); event.currentTarget.blur(); } }}
    onChange={event => {
      const input = event.target;
      setValue(input.value === '' ? null : numeric ? input.valueAsNumber : input.value);
    }} />;
}
