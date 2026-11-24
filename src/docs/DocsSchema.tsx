import { useState } from 'react';
import { Dialog, ErrorMessage, message } from '../ui';
import { DocsForm, FieldFields, fieldInput, formulaInput, FormulaFields } from './DocsForms';
import { aggregationNames, propertyNames, type Aggregation, type CollectionSummary, type DocCollection, type DocsApi, type PropertyField } from './api';
import { useCollection } from './useCollection';

function AggregationDetails({ aggregation, collection, api }: { aggregation: Aggregation; collection: DocCollection; api: DocsApi }) {
  const relation = collection.fields.find(field => field.id === aggregation.relationFieldId);
  const target = useCollection(api, aggregation.sourceFieldId ? relation?.targetCollectionId : undefined, 0);
  const source = target?.collection?.fields.find(field => field.id === aggregation.sourceFieldId);
  return <>
    <p className="docs-view-summary">Relation · {relation?.name ?? 'Indisponible'}</p>
    {aggregation.sourceFieldId && <p className="docs-view-summary">Propriété source · {source?.name ?? (target ? 'Indisponible' : 'Chargement…')}</p>}
    <p className="docs-view-summary">Calcul · {aggregationNames[aggregation.operation]}</p>
  </>;
}

export function SchemaDialog({ collection, collections, api, close, changed }: {
  collection: DocCollection; collections: CollectionSummary[]; api: DocsApi; close: () => void;
  changed: (fields: PropertyField[], refresh: boolean) => void;
}) {
  const [selected, setSelected] = useState<PropertyField | 'new'>();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');

  async function reorder(index: number, offset: number) {
    if (pending) return;
    const ids = collection.fields.map(field => field.id);
    const other = index + offset;
    [ids[index], ids[other]] = [ids[other], ids[index]];
    setPending(true); setError('');
    try { changed(await api.orderFields(collection.id, ids), false); }
    catch (reason) { setError(message(reason)); }
    finally { setPending(false); }
  }

  if (selected === 'new') return <DocsForm title="Nouvelle propriété" action="Ajouter la propriété"
    close={() => setSelected(undefined)} submit={async data => {
      const field = await api.createField(collection.id, fieldInput(data, collection.fields));
      changed([...collection.fields, field], field.kind === 'aggregate' || field.kind === 'formula');
    }}><FieldFields collections={collections} collection={collection} api={api} /></DocsForm>;

  if (selected) return <DocsForm title="Modifier la propriété" action="Enregistrer" close={() => setSelected(undefined)}
    submit={async data => {
      const options = data.getAll('option').map(value => String(value).trim());
      const extra = String(data.get('extra') ?? '').trim();
      if (extra) options.push(extra);
      const formula = selected.kind === 'formula'
        ? { expression: formulaInput(String(data.get('formula') ?? ''), collection.fields) } : undefined;
      const saved = await api.editField(collection.id, selected.id, { name: String(data.get('name')), previousOptions: selected.options, options, ...(formula && { formula }) });
      changed(collection.fields.map(field => field.id === saved.id ? saved : field), true);
    }}>
    <label>Nom<input name="name" defaultValue={selected.name} maxLength={160} required /></label>
    <p className="docs-view-summary">Type · {propertyNames[selected.kind]}</p>
    {selected.kind === 'relation' && <p className="docs-view-summary">
      Collection cible · {collections.find(item => item.id === selected.targetCollectionId)?.title ?? 'Indisponible'}
    </p>}
    {selected.aggregation && <AggregationDetails aggregation={selected.aggregation} collection={collection} api={api} />}
    {selected.kind === 'formula' && <FormulaFields collection={collection} initial={selected.formula?.expression ?? ''} />}
    {selected.options.length > 0 && <fieldset className="docs-view-settings"><legend>Options</legend>
      <p>Les choix restent associés aux pages après un changement de libellé.</p>
      {selected.options.map((option, index) => <label key={option}>Option {index + 1}
        <input name="option" defaultValue={option} maxLength={120} required />
      </label>)}
      {selected.options.length < 50 && <label>Ajouter une option<input name="extra" maxLength={120} /></label>}
    </fieldset>}
  </DocsForm>;

  return <Dialog title="Propriétés de la collection" onClose={close} pending={pending}>
    <div className="form-body">
      {collection.fields.map((field, index) => <div className="docs-schema-property" key={field.id}>
        <div><strong>{field.name}</strong><small>{propertyNames[field.kind]}{field.kind === 'relation' &&
          ' vers ' + (collections.find(item => item.id === field.targetCollectionId)?.title ?? 'une collection indisponible')}
          {field.aggregation && ' · ' + aggregationNames[field.aggregation.operation]}
          {field.formula && ' · Formule'}</small></div>
        <div className="docs-row">
          <button className="button" disabled={pending} aria-label={'Modifier ' + field.name} onClick={() => setSelected(field)}>Modifier</button>
          <button className="button" disabled={pending || index === 0} aria-label={'Remonter ' + field.name} onClick={() => void reorder(index, -1)}>↑</button>
          <button className="button" disabled={pending || index === collection.fields.length - 1}
            aria-label={'Descendre ' + field.name} onClick={() => void reorder(index, 1)}>↓</button>
        </div>
      </div>)}
      {!collection.fields.length && <p>Cette collection ne contient aucune propriété.</p>}
      <ErrorMessage>{error}</ErrorMessage>
      {collection.fields.length < 50 && <button className="button" disabled={pending} onClick={() => setSelected('new')}>Ajouter une propriété</button>}
    </div>
    <div className="dialog-footer"><button className="button" disabled={pending} onClick={close}>Fermer</button></div>
  </Dialog>;
}
