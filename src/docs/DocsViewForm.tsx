import { useState } from 'react';
import { DocsForm, ValueInput } from './DocsForms';
import { layoutChoices, supportsGrouping, viewSettings } from './collection-views';
import type { DocCollection, DocView, FilterGroup, FilterOperator, FilterRule, FilterTree, Layout, PropertyField, ScalarValue, SortRule, ViewInput } from './api';

const modes = { all: 'Toutes les conditions (ET)', any: 'Une condition suffit (OU)' };
const commonOperators: [FilterOperator, string][] = [['empty', 'Est vide'], ['filled', 'Est renseignée']];
const modeOptions = Object.entries(modes).map(([key, label]) => <option key={key} value={key}>{label}</option>);

function operators(field: PropertyField): [FilterOperator, string][] {
  if (field.kind === 'multi') return [['contains', 'Contient l’option'], ...commonOperators];
  const list: [FilterOperator, string][] = [['eq', 'Est égal à']];
  if (field.kind === 'url' || field.kind === 'text') list.push(['contains', 'Contient']);
  if (field.kind === 'number' || field.kind === 'aggregate' || field.kind === 'formula') list.push(['gte', 'Supérieur ou égal à'], ['lte', 'Inférieur ou égal à']);
  if (field.kind === 'date') list.push(['gte', 'Le ou après'], ['lte', 'Le ou avant']);
  return [...list, ...commonOperators];
}

function freshRule(field: PropertyField): FilterRule {
  const initial = field.options[0] ?? (field.kind === 'checkbox' ? false : null);
  return { fieldId: field.id, operator: field.kind === 'multi' ? 'contains' : 'eq', value: initial };
}

function Condition({ rule, fields, change, remove }: {
  rule: FilterRule; fields: PropertyField[]; change: (value: FilterRule) => void; remove: () => void;
}) {
  const field = fields.find(item => item.id === rule.fieldId);
  if (!field) return null;
  const valueLabel = rule.operator === 'eq' ? 'Est égal à' : 'Valeur';
  const takesValue = rule.operator !== 'empty' && rule.operator !== 'filled';
  return <div className="docs-filter">
    <select aria-label="Propriété du filtre" value={rule.fieldId} onChange={event => {
      const next = fields.find(item => item.id === event.target.value);
      if (next) change(freshRule(next));
    }}>{fields.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
    <select aria-label="Opérateur" value={rule.operator} onChange={event => {
      const operator = event.target.value as FilterOperator;
      const value = operator === 'empty' || operator === 'filled' ? null : rule.value ?? freshRule(field).value;
      change({ ...rule, operator, value });
    }}>{operators(field).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
    {takesValue && <label>{valueLabel}
      <ValueInput field={field.kind === 'url' && rule.operator === 'contains' ? { ...field, kind: 'text' } : field}
        value={rule.value} label={valueLabel} filter setValue={value => change({ ...rule, value: value as ScalarValue })} />
    </label>}
    <button className="button" type="button" onClick={remove}>Retirer le filtre</button>
  </div>;
}

export function ViewForm({ collection, view, close, save }: {
  collection: DocCollection; view?: DocView; close: () => void; save: (data: ViewInput) => Promise<void>;
}) {
  const initial = viewSettings(view);
  const { fields } = collection;
  const [layout, setLayout] = useState(initial.layout);
  const [groupBy, setGroup] = useState(initial.groupBy);
  const dateFields = fields.filter(field => field.kind === 'date');
  const [dateFieldId, setDateFieldId] = useState<string | null>(() =>
    dateFields.some(field => field.id === initial.dateFieldId) ? initial.dateFieldId : dateFields[0]?.id ?? null);
  const [endDateFieldId, setEndDateFieldId] = useState<string | null>(() => {
    const startId = dateFields.some(field => field.id === initial.dateFieldId) ? initial.dateFieldId : dateFields[0]?.id ?? null;
    return dateFields.some(field => field.id === initial.endDateFieldId && field.id !== startId)
      ? initial.endDateFieldId ?? null : dateFields.find(field => field.id !== startId)?.id ?? null;
  });
  function changeStartField(nextStart: string | null) {
    setDateFieldId(nextStart);
    setEndDateFieldId(current => current === nextStart
      ? dateFields.find(field => field.id !== nextStart)?.id ?? null : current);
  }
  const [filterTree, setTree] = useState(initial.filterTree);
  const [sorts, setSorts] = useState(initial.sorts);
  const filterCount = filterTree.conditions.reduce((total, item) => total + ('conditions' in item ? item.conditions.length : 1), 0);
  const filterFields = fields.filter(field => field.kind !== 'relation');
  const first = filterFields[0];
  const sortChoices = [{ id: 'title', name: 'Titre' }, ...filterFields.filter(field => field.kind !== 'multi')];

  function replaceFilter(index: number, item?: FilterTree['conditions'][number]) {
    setTree(tree => ({ ...tree, conditions: item ? tree.conditions.map((current, position) => position === index ? item : current)
      : tree.conditions.filter((_, position) => position !== index) }));
  }
  function appendFilter(item: FilterTree['conditions'][number]) {
    setTree(tree => ({ ...tree, conditions: [...tree.conditions, item] }));
  }
  function changeSort(index: number, patch: Partial<SortRule>) {
    setSorts(current => current.map((rule, position) => position === index ? { ...rule, ...patch } : rule));
  }
  function promoteSort(index: number) {
    setSorts(current => [...current.slice(0, index - 1), current[index], current[index - 1], ...current.slice(index + 1)]);
  }
  const unusedSort = sortChoices.find(choice => !sorts.some(sort => sort.fieldId === choice.id));

  return <DocsForm title={view ? 'Configurer la vue' : 'Nouvelle vue'} action="Enregistrer" close={close} submit={data => save({
    name: String(data.get('name')), filterTree, groupBy, dateFieldId,
    ...(layout === 'timeline' ? { endDateFieldId } : {}), layout, sorts,
    hidden: fields.filter(field => !data.getAll('visible').includes(field.id)).map(field => field.id),
  })}>
    <div className="docs-view-form-grid">
      <label>Nom de la vue<input name="name" required maxLength={160} defaultValue={initial.name} /></label>
      <label>Présentation<select aria-label="Présentation" value={layout} onChange={event => {
        const value = event.target.value as Layout;
        if (groupBy && !fields.some(field => field.id === groupBy && supportsGrouping(field.kind, value))) setGroup(null);
        setLayout(value);
      }}>{layoutChoices.map(([key, label]) => <option key={key} value={key}
        disabled={key === 'calendar' && dateFields.length === 0 || key === 'timeline' && dateFields.length < 2}>{label}</option>)}</select></label>
    </div>
    {layout === 'calendar' && <>
      <label>Propriété Date<select aria-label="Propriété Date" required value={dateFieldId ?? ''} onChange={event => changeStartField(event.target.value || null)}>
        <option value="">Choisir une propriété Date</option>
        {dateFields.map(field => <option key={field.id} value={field.id}>{field.name}</option>)}
      </select></label>
      {dateFields.length === 0
        ? <small>Ajoutez d’abord une propriété Date à cette collection.</small>
        : <small>Les pages sans valeur restent dans la section « Sans date ».</small>}
    </>}
    {layout === 'timeline' && <div className="docs-timeline-settings">
      <label>Propriété de début<select aria-label="Propriété de début" required value={dateFieldId ?? ''} onChange={event => changeStartField(event.target.value || null)}>
        <option value="">Choisir une propriété Date</option>{dateFields.map(field => <option key={field.id} value={field.id}>{field.name}</option>)}
      </select></label>
      <label>Propriété de fin<select aria-label="Propriété de fin" required value={endDateFieldId ?? ''} onChange={event => setEndDateFieldId(event.target.value || null)}>
        <option value="">Choisir une propriété Date</option>{dateFields.map(field => <option key={field.id} value={field.id} disabled={field.id === dateFieldId}>{field.name}</option>)}
      </select></label>
      {dateFields.length < 2 && <small>Ajoutez deux propriétés Date distinctes à cette collection.</small>}
    </div>}
    {layout !== 'gallery' && <label>Regrouper par<select aria-label="Regrouper par" value={groupBy ?? ''} onChange={event => setGroup(event.target.value || null)}>
      <option value="">{layout === 'board' ? 'Choisir une propriété' : 'Aucun'}</option>
      {fields.filter(field => supportsGrouping(field.kind, layout)).map(field => <option key={field.id} value={field.id}>{field.name}</option>)}
    </select></label>}
    {layout === 'gallery' && <small>La carte reprend la première image privée du contenu enregistré de la page.</small>}
    <fieldset className="docs-view-settings"><legend>Filtres</legend>
      <label>Combiner les conditions<select aria-label="Combiner les conditions" value={filterTree.mode}
        onChange={event => setTree(tree => ({ ...tree, mode: event.target.value as FilterTree['mode'] }))}>{modeOptions}</select></label>
      {filterTree.conditions.map((item, index) => {
        if (!('conditions' in item)) return <Condition key={index} rule={item} fields={filterFields}
          change={value => replaceFilter(index, value)} remove={() => replaceFilter(index)} />;
        const changeGroup = (patch: Partial<FilterGroup>) => replaceFilter(index, { ...item, ...patch });
        return <div className="docs-filter-group" key={index}>
          <label>Groupe {index + 1}<select aria-label={'Combiner le groupe ' + (index + 1)} value={item.mode}
            onChange={event => changeGroup({ mode: event.target.value as FilterGroup['mode'] })}>{modeOptions}</select></label>
          {item.conditions.map((rule, position) => <Condition key={position} rule={rule} fields={filterFields}
            change={value => changeGroup({ conditions: item.conditions.map((other, i) => i === position ? value : other) })}
            remove={() => {
              if (item.conditions.length === 1) replaceFilter(index);
              else changeGroup({ conditions: item.conditions.filter((_, i) => i !== position) });
            }} />)}
          <div className="docs-row">
            {first && filterCount < 20 && <button className="button" type="button"
              onClick={() => changeGroup({ conditions: [...item.conditions, freshRule(first)] })}>Ajouter une condition au groupe</button>}
            <button className="button" type="button" onClick={() => replaceFilter(index)}>Retirer le groupe</button>
          </div>
        </div>;
      })}
      {first && filterCount < 20 && <div className="docs-row">
        <button className="button" type="button" onClick={() => appendFilter(freshRule(first))}>Ajouter un filtre</button>
        {filterCount <= 18 && <button className="button" type="button"
          onClick={() => appendFilter({ mode: 'any', conditions: [freshRule(first), freshRule(first)] })}>Ajouter un groupe</button>}
      </div>}
    </fieldset>
    <fieldset className="docs-view-settings"><legend>Tris, par ordre de priorité</legend>
      {sorts.map((rule, index) => <div className="docs-sort-rule" key={index}>
        <select aria-label={'Propriété du tri ' + (index + 1)} value={rule.fieldId} onChange={event => changeSort(index, { fieldId: event.target.value })}>
          {sortChoices.map(field => <option key={field.id} value={field.id}
            disabled={field.id !== rule.fieldId && sorts.some(other => other.fieldId === field.id)}>{field.name}</option>)}
        </select>
        <select aria-label={'Ordre du tri ' + (index + 1)} value={rule.direction}
          onChange={event => changeSort(index, { direction: event.target.value === 'desc' ? 'desc' : 'asc' })}>
          <option value="asc">Croissant</option><option value="desc">Décroissant</option>
        </select>
        <div className="docs-row">
          <button className="button" type="button" disabled={!index} aria-label={'Remonter le tri ' + (index + 1)} onClick={() => promoteSort(index)}>↑</button>
          <button className="button" type="button" aria-label={'Retirer le tri ' + (index + 1)}
            onClick={() => setSorts(current => current.filter((_, position) => position !== index))}>Retirer</button>
        </div>
      </div>)}
      {unusedSort && <button className="button" type="button" onClick={() => setSorts(current => [...current,
        { fieldId: unusedSort.id, direction: 'asc' }])}>Ajouter un tri</button>}
    </fieldset>
    {fields.length > 0 && <fieldset className="docs-view-settings"><legend>Propriétés visibles</legend><div className="docs-row">
      {fields.map(field => <label className="docs-column" key={field.id}>
        <input type="checkbox" name="visible" value={field.id} defaultChecked={!initial.hidden.includes(field.id)} />{field.name}
      </label>)}
    </div></fieldset>}
  </DocsForm>;
}
