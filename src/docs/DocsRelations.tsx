import { useState } from 'react';
import { DocsForm, pagePath } from './DocsForms';
import { DocLink } from './DocsLink';
import type { CollectionSummary, OpenDoc, PageSummary, PropertyField, RelationUpdate } from './api';

export type SaveRelations = (pageId: string, fieldId: string, change: RelationUpdate) => Promise<void>;

function relationIds(page: PageSummary, field: PropertyField) {
  const value = page.properties[field.id];
  return Array.isArray(value) ? value : [];
}

function path(page: PageSummary, pages: ReadonlyMap<string, PageSummary>, collection: string) {
  return [collection, ...pagePath(page, pages).slice(0, -1)].join(' / ');
}

type RelationProps = {
  page: PageSummary;
  field: PropertyField;
  pages: ReadonlyMap<string, PageSummary>;
  target: CollectionSummary | undefined;
  open: OpenDoc;
};

export function RelationLinks({ page, field, pages, target, open }: RelationProps) {
  const ids = relationIds(page, field);
  const targets = ids.flatMap(id => {
    const candidate = pages.get(id);
    return candidate && candidate.collectionId === field.targetCollectionId ? [candidate] : [];
  });
  return <div className="docs-relation-links">
    {targets.length ? targets.map(item => <DocLink key={item.id} entry={item} open={open}
      relationContext={path(item, pages, target?.title ?? 'Collection')} />) : <span>—</span>}
  </div>;
}

function normalize(value: string) {
  return value.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLocaleLowerCase('fr');
}

function RelationPicker({ page, field, pages, target, save, close }: Omit<RelationProps, 'open'> & {
  save: SaveRelations; close: () => void;
}) {
  const [initial] = useState(() => relationIds(page, field));
  const [selected, setSelected] = useState(() => new Set(initial));
  const [query, setQuery] = useState('');
  const term = normalize(query.trim());
  const candidates = [...pages.values()].filter(candidate => candidate.collectionId === field.targetCollectionId);
  const choices = candidates.filter(candidate => normalize(candidate.title).includes(term));
  const unavailable = [...selected].filter(id => !initial.includes(id) && pages.get(id)?.collectionId !== field.targetCollectionId);
  const count = candidates.filter(candidate => selected.has(candidate.id)).length;
  const targetTitle = target?.title ?? 'la collection cible';

  return <DocsForm title={field.name + ' · ' + page.title} action="Enregistrer" close={close} submit={async () => {
    if (unavailable.length) throw new Error('Retirez les pages devenues indisponibles avant d’enregistrer.');
    const add = [...selected].filter(id => !initial.includes(id));
    const remove = initial.filter(id => !selected.has(id));
    if (add.length || remove.length) await save(page.id, field.id, { add, remove });
  }}>
    <label>Rechercher une page<input type="search" aria-label="Rechercher une page" placeholder="Rechercher par titre…"
      maxLength={200} value={query} onChange={event => setQuery(event.target.value)} /></label>
    <fieldset className="docs-view-settings docs-relation-picker"><legend>Pages de {targetTitle}</legend>
      {choices.map(candidate => <label key={candidate.id} className="docs-relation-choice">
        <input type="checkbox" checked={selected.has(candidate.id)} onChange={event => {
          const checked = event.currentTarget.checked;
          setSelected(current => {
            const next = new Set(current);
            if (checked) next.add(candidate.id);
            else next.delete(candidate.id);
            return next;
          });
        }} />
        <span>{candidate.title}<small>{path(candidate, pages, targetTitle)}</small></span>
      </label>)}
      {!choices.length && <p>Aucune page disponible.</p>}
    </fieldset>
    <p className="docs-view-summary" aria-live="polite">{count} {count === 1 ? 'page liée' : 'pages liées'}</p>
    {!!unavailable.length && <div className="docs-row">
      <p>Des pages sélectionnées sont devenues indisponibles.</p>
      <button type="button" className="button" onClick={() =>
        setSelected(current => new Set([...current].filter(id => !unavailable.includes(id))))}>Actualiser la sélection</button>
    </div>}
  </DocsForm>;
}

export function RelationCell({ save, ...props }: RelationProps & { save?: SaveRelations }) {
  const [editing, setEditing] = useState(false);
  const { page, field, pages, target } = props;
  const linked = relationIds(page, field).some(id => pages.get(id)?.collectionId === field.targetCollectionId);
  const action = linked ? 'Modifier' : 'Ajouter';
  return <div className="docs-relation-cell">
    <RelationLinks {...props} />
    {save && target && <button type="button" className="button subtle" aria-label={action + ' ' + field.name + ' — ' + page.title}
      onClick={() => setEditing(true)}>{action}</button>}
    {save && editing && target && <RelationPicker page={page} field={field} pages={pages} target={target}
      save={save} close={() => setEditing(false)} />}
  </div>;
}
