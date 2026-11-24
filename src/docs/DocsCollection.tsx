import { useId, useRef, useState } from 'react';
import { Images, Plus, Table } from '@phosphor-icons/react';
import { ErrorMessage, message } from '../ui';
import { DocsForm, ValueInput } from './DocsForms';
import { DocLink } from './DocsLink';
import { RelationCell, RelationLinks, type SaveRelations } from './DocsRelations';
import { DocsTimeline } from './DocsTimeline';
import { DocsGallery } from './DocsGallery';
import type { OpenGalleryPage } from './gallery-navigation';
import { compareViewRows, groupOptions, isAggregateError, valueLabel, viewRows, viewSettings } from './collection-views';
import { calculationErrors, type CollectionSummary, type DocCollection, type DocView, type DocsApi, type OpenDoc, type PageSummary, type PropertyField, type PropertyValue } from './api';

export function Cell({ page, field, update, table }: {
  page: PageSummary; field: PropertyField; update?: (id: string, field: string, value: PropertyValue) => Promise<void>; table?: boolean;
}) {
  const stored = page.properties[field.id] ?? null;
  const current = isAggregateError(stored) ? null : stored;
  const [openEditor, setOpenEditor] = useState(false);
  const label = table ? field.name + ' — ' + page.title : field.name;
  const [edit, setEdit] = useState<{ value: PropertyValue }>();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  async function save(value: PropertyValue) {
    if (!update) return;
    if (value === current) { setEdit(undefined); return; }
    setPending(true);
    setError('');
    try { await update(page.id, field.id, value); setEdit(undefined); }
    catch (reason) { setError(message(reason)); }
    finally { setPending(false); }
  }
  if (field.kind === 'aggregate' || field.kind === 'formula') return <AggregateValue page={page} field={field} />;
  if (!update) return <span>{field.kind === 'url' && typeof current === 'string' && /^https?:\/\//i.test(current)
    ? <a href={current} target="_blank" rel="noreferrer">{current}</a> : valueLabel(current) || '—'}</span>;
  if (field.kind === 'url' || field.kind === 'multi') return <div className="docs-cell docs-complex-value">
    <span>{field.kind === 'url' && typeof current === 'string' && /^https?:\/\//i.test(current)
      ? <a href={current} target="_blank" rel="noreferrer">{current}</a> : valueLabel(current) || '—'}</span>
    <button type="button" className="button subtle" aria-label={'Modifier ' + label} onClick={() => setOpenEditor(true)}>Modifier</button>
    {openEditor && <DocsForm title={'Modifier ' + field.name} action="Enregistrer" close={() => setOpenEditor(false)}
      submit={async data => {
        const value = field.kind === 'multi' ? data.getAll('values').map(String) : String(data.get('url')).trim() || null;
        await update(page.id, field.id, value);
      }}>
      {field.kind === 'url' ? <label>Adresse URL<input type="url" name="url" maxLength={2048}
        defaultValue={typeof current === 'string' ? current : ''} /></label>
        : <fieldset className="docs-view-settings"><legend>Choisir les options</legend>{field.options.map(option =>
          <label className="docs-column" key={option}><input type="checkbox" name="values" value={option}
            defaultChecked={Array.isArray(current) && current.includes(option)} />{option}</label>)}</fieldset>}
    </DocsForm>}
  </div>;
  return <div className="docs-cell">
    <ValueInput field={field} value={edit ? edit.value : current} label={label}
      disabled={pending} setValue={value => {
        setEdit({ value });
        if (field.kind === 'checkbox' || field.kind === 'select' || field.kind === 'date') void save(value);
      }} onBlur={() => {
        if (edit && (field.kind === 'text' || field.kind === 'number')) void save(edit.value);
      }} />
    <ErrorMessage>{error}</ErrorMessage>
    {error && edit && <button type="button" className="button" onClick={() => void save(edit.value)}>Réessayer</button>}
  </div>;
}

const aggregateNumber = new Intl.NumberFormat('fr-FR', { maximumSignificantDigits: 17 });
function AggregateValue({ page, field }: { page: PageSummary; field: PropertyField }) {
  const value = page.properties[field.id] ?? null;
  return <span className={isAggregateError(value) ? 'docs-aggregate-error' : undefined}>
    {typeof value === 'number' ? aggregateNumber.format(value) : value && typeof value === 'object' && !Array.isArray(value)
      ? calculationErrors[value.error] : valueLabel(value) || 'Sans valeur'}
  </span>;
}

const boardDragType = 'application/x-circular-doc-page';
type Update = (pageId: string, fieldId: string, value: PropertyValue) => Promise<void>;

function isoDate(date: Date) {
  return [date.getFullYear(), String(date.getMonth() + 1).padStart(2, '0'), String(date.getDate()).padStart(2, '0')].join('-');
}

function utcIsoDate(date: Date) {
  return [String(date.getUTCFullYear()).padStart(4, '0'), String(date.getUTCMonth() + 1).padStart(2, '0'), String(date.getUTCDate()).padStart(2, '0')].join('-');
}

function utcCalendarDate(year: number, month: number, day: number) {
  const date = new Date(0);
  date.setUTCFullYear(year, month, day);
  date.setUTCHours(0, 0, 0, 0);
  return date;
}

function utcDate(value: string) {
  const [year, month, day] = value.split('-').map(Number);
  return utcCalendarDate(year, month - 1, day);
}

function CalendarEvent({ page, dateFieldId, fields, pageMap, collectionMap, open }: {
  page: PageSummary; dateFieldId: string; fields: PropertyField[]; pageMap: Map<string, PageSummary>;
  collectionMap: Map<string, CollectionSummary>; open: OpenDoc;
}) {
  const date = page.properties[dateFieldId];
  const label = typeof date === 'string' ? new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'short', timeZone: 'UTC' }).format(utcDate(date)) : '';
  return <article className="docs-calendar-event">
    <DocLink entry={page} open={open} />
    <small className="docs-calendar-event-date">{label}</small>
    {fields.length > 0 && <dl className="docs-calendar-properties">{fields.map(field => <div key={field.id}>
      <dt>{field.name}</dt><dd>{field.kind === 'relation'
        ? <RelationLinks page={page} field={field} pages={pageMap} target={collectionMap.get(field.targetCollectionId ?? '')} open={open} />
        : <Cell page={page} field={field} />}</dd>
    </div>)}</dl>}
  </article>;
}

function CalendarView({ rows, collection, fields, dateFieldId, sorts, pageMap, collectionMap, open }: {
  rows: PageSummary[]; collection: DocCollection; fields: PropertyField[]; dateFieldId: string | null;
  sorts: ReturnType<typeof viewSettings>['sorts']; pageMap: Map<string, PageSummary>; collectionMap: Map<string, CollectionSummary>; open: OpenDoc;
}) {
  const undatedTitleId = useId();
  const [month, setMonth] = useState(() => {
    const today = new Date();
    return utcCalendarDate(today.getFullYear(), today.getMonth(), 1);
  });
  const selected = collection.fields.find(field => field.id === dateFieldId && field.kind === 'date');
  if (!selected) return <p className="docs-view-empty">Cette vue doit être configurée avec une propriété Date.</p>;

  const hasDate = (page: PageSummary) => typeof page.properties[selected.id] === 'string' &&
    /^\d{4}-\d{2}-\d{2}$/.test(page.properties[selected.id] as string);
  const dated = rows.filter(hasDate);
  const undated = rows.filter(page => !hasDate(page));
  const monthRows = dated.filter(page => {
    const [year, monthNumber] = String(page.properties[selected.id]).split('-').map(Number);
    return year === month.getUTCFullYear() && monthNumber === month.getUTCMonth() + 1;
  });
  const offset = (utcCalendarDate(month.getUTCFullYear(), month.getUTCMonth(), 1).getUTCDay() + 6) % 7;
  const totalDays = utcCalendarDate(month.getUTCFullYear(), month.getUTCMonth() + 1, 0).getUTCDate();
  const cellCount = Math.ceil((offset + totalDays) / 7) * 7;
  const gridStart = utcCalendarDate(month.getUTCFullYear(), month.getUTCMonth(), 1 - offset);
  const gridEnd = utcCalendarDate(gridStart.getUTCFullYear(), gridStart.getUTCMonth(), gridStart.getUTCDate() + cellCount);
  const gridRows = dated.filter(page => {
    const date = utcDate(String(page.properties[selected.id]));
    return date >= gridStart && date < gridEnd;
  });
  const orderRows = (items: PageSummary[]) => [...items].sort((left, right) => {
    const leftDate = String(left.properties[selected.id]);
    const rightDate = String(right.properties[selected.id]);
    return leftDate.localeCompare(rightDate) || compareViewRows(left, right, sorts) ||
      left.title.localeCompare(right.title, 'fr') || left.id.localeCompare(right.id);
  });
  const orderedRows = orderRows(monthRows);
  const orderedGridRows = orderRows(gridRows);
  const dayGroups = [...new Set(orderedRows.map(page => String(page.properties[selected.id])))].map(date => ({
    date, pages: orderedRows.filter(page => page.properties[selected.id] === date),
  }));
  const today = isoDate(new Date());
  const monthLabel = new Intl.DateTimeFormat('fr-FR', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(month);
  const weekdays = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'];
  const eventFields = fields.filter(field => field.id !== selected.id);

  return <>
    <section className="docs-calendar" aria-label="Calendrier du mois">
      <header className="docs-calendar-header">
        <div className="docs-row">
          <button type="button" className="button" aria-label="Mois précédent"
            onClick={() => setMonth(value => utcCalendarDate(value.getUTCFullYear(), value.getUTCMonth() - 1, 1))}>←</button>
          <button type="button" className="button" onClick={() => {
            const current = new Date(); setMonth(utcCalendarDate(current.getFullYear(), current.getMonth(), 1));
          }}>Aujourd’hui</button>
          <button type="button" className="button" aria-label="Mois suivant"
            onClick={() => setMonth(value => utcCalendarDate(value.getUTCFullYear(), value.getUTCMonth() + 1, 1))}>→</button>
        </div>
        <h2 aria-live="polite">{monthLabel}</h2>
        <p className="docs-calendar-date-field">Date · <strong>{selected.name}</strong></p>
      </header>
      {!monthRows.length && <p className="docs-view-empty docs-calendar-month-empty">Aucune échéance ce mois-ci.</p>}
      <div className="docs-calendar-week" aria-hidden="true">{weekdays.map(day => <div key={day}>{day.slice(0, 3)}</div>)}</div>
      <div className="docs-calendar-grid" role="table" aria-label={monthLabel}>
        {Array.from({ length: cellCount / 7 }, (_, week) => <div className="docs-calendar-week-row" role="row" key={week}>
          {weekdays.map((_, column) => {
            const day = week * 7 + column;
            const date = utcCalendarDate(gridStart.getUTCFullYear(), gridStart.getUTCMonth(), gridStart.getUTCDate() + day);
            const value = utcIsoDate(date);
            const events = orderedGridRows.filter(page => page.properties[selected.id] === value);
            return <div key={value} role="cell" aria-label={new Intl.DateTimeFormat('fr-FR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }).format(date)}
              className={'docs-calendar-day' + (date.getUTCMonth() !== month.getUTCMonth() ? ' is-outside' : '') + (value === today ? ' is-today' : '')}>
              <div className="docs-calendar-day-heading"><strong>{date.getUTCDate()}</strong>{value === today && <small>Aujourd’hui</small>}</div>
              <div className="docs-calendar-day-events">{events.map(page => <CalendarEvent key={page.id} page={page} dateFieldId={selected.id}
                fields={eventFields} pageMap={pageMap} collectionMap={collectionMap} open={open} />)}</div>
            </div>;
          })}
        </div>)}
      </div>
      <div className="docs-calendar-agenda" role="region" aria-label="Agenda du mois">
        {!monthRows.length ? <p className="docs-view-empty">Aucune échéance ce mois-ci.</p> : dayGroups.map(group => <section className="docs-calendar-agenda-day" key={group.date}>
          <h3>{new Intl.DateTimeFormat('fr-FR', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'UTC' }).format(utcDate(group.date))}</h3>
          {group.pages.map(page => <CalendarEvent key={page.id} page={page} dateFieldId={selected.id}
            fields={eventFields} pageMap={pageMap} collectionMap={collectionMap} open={open} />)}
        </section>)}
      </div>
    </section>
    <section className="docs-calendar-undated" aria-labelledby={undatedTitleId}>
      <header><div><h2 id={undatedTitleId}>Sans date</h2><small>Pages actives sans valeur dans « {selected.name} »</small></div>
        <span>{undated.length} {undated.length === 1 ? 'page' : 'pages'}</span></header>
      {!undated.length ? <p className="docs-view-empty">Aucune page sans date pour ces filtres.</p> :
        <ul>{undated.map(page => <li key={page.id}><CalendarEvent page={page} dateFieldId={selected.id}
          fields={eventFields} pageMap={pageMap} collectionMap={collectionMap} open={open} /></li>)}</ul>}
    </section>
  </>;
}

export function CollectionRows({ collection, view, pages, collections, open, editing, api, openGalleryPage, galleryOrigin }: {
  collection: DocCollection; view: DocView; pages: PageSummary[]; collections: CollectionSummary[]; open: OpenDoc;
  editing?: { update: Update; saveRelations: SaveRelations; newField: () => void }; api: DocsApi;
  openGalleryPage: OpenGalleryPage; galleryOrigin: { kind: 'collection' | 'embedded'; destinationId: string; viewId?: string; blockIndex?: number };
}) {
  const settings = viewSettings(view);
  const fields = collection.fields.filter(field => !settings.hidden.includes(field.id));
  const rows = viewRows(pages, collection.id, settings);
  const pageMap = new Map(pages.map(page => [page.id, page]));
  const collectionMap = new Map(collections.map(item => [item.id, item]));
  const relations = fields.filter(field => field.kind === 'relation');
  const aggregates = fields.filter(field => field.kind === 'aggregate');
  const group = collection.fields.find(field => field.id === settings.groupBy);
  const groups = group ? groupOptions(group).map(item => ({
    ...item, pages: rows.filter(page => (page.properties[group.id] ?? null) === item.value),
  })) : [];
  const [moving, setMoving] = useState<string>();
  const [dragOver, setDragOver] = useState<string>();
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const inFlight = useRef(false);
  const empty = settings.filterTree.conditions.length ? 'Aucune page ne correspond aux filtres.' : 'Cette collection est vide.';
  const movePage = moving ? rows.find(item => item.id === moving) : undefined;

  async function move(page: PageSummary, value: string | null) {
    if (!editing || !group || inFlight.current || (page.properties[group.id] ?? null) === value) return;
    inFlight.current = true;
    setPending(true); setNotice(''); setError('');
    try {
      await editing.update(page.id, group.id, value);
      setNotice('« ' + page.title + ' » déplacée vers « ' + (value ?? 'Sans valeur') + ' ».');
    } finally { inFlight.current = false; setPending(false); }
  }

  const fieldsSummary = (page: PageSummary, skip?: string) => fields.filter(field => field.id !== skip &&
    !['relation', 'aggregate', 'formula'].includes(field.kind))
    .map(field => valueLabel(page.properties[field.id] ?? null)).filter(Boolean).join(' · ');

  function relationSummary(page: PageSummary) {
    return relations.filter(field => page.properties[field.id]).map(field => <div className="docs-relation-summary" key={field.id}>
      <small>{field.name}</small>
      <RelationLinks page={page} field={field} pages={pageMap} target={collectionMap.get(field.targetCollectionId ?? '')} open={open} />
    </div>);
  }

  function aggregateSummary(page: PageSummary) {
    const formulas = fields.filter(field => field.kind === 'formula');
    return [...aggregates, ...formulas].map(field => <div className="docs-relation-summary" key={field.id}>
      <small>{field.name}</small><AggregateValue page={page} field={field} />
    </div>);
  }

  function renderRows(items: PageSummary[]) {
    if (settings.layout === 'list') return items.length ? <ul className="docs-collection-list">{items.map(page => <li key={page.id}>
      <DocLink entry={page} open={open} /><small>{fieldsSummary(page)}</small>{relationSummary(page)}{aggregateSummary(page)}
    </li>)}</ul> : <p className="docs-view-empty">{empty}</p>;
    return <div className="docs-table" role="region" aria-label="Tableau des pages" tabIndex={0}><table>
      <thead><tr><th scope="col">Titre</th>{fields.map(field => <th scope="col" key={field.id}>{field.name}</th>)}</tr></thead>
      <tbody>{items.length ? items.map(page => <tr key={page.id}>
        <td><DocLink entry={page} open={open} /></td>
        {fields.map(field => <td key={field.id}>{field.kind === 'relation'
          ? <RelationCell page={page} field={field} pages={pageMap} target={collectionMap.get(field.targetCollectionId ?? '')}
            open={open} save={editing?.saveRelations} />
          : <Cell page={page} field={field} update={editing?.update} table />}</td>)}
      </tr>) : <tr><td className="docs-empty" colSpan={fields.length + 1}>{empty}</td></tr>}</tbody>
    </table></div>;
  }

  return <>
    <p className="docs-view-summary">{rows.length} {rows.length === 1 ? 'page' : 'pages'}{group && ' · Groupe : ' + group.name}</p>
    {notice && <p className="docs-lifecycle-notice" role="status">{notice}</p>}
    <ErrorMessage>{error}</ErrorMessage>
    {settings.layout === 'gallery' ? <DocsGallery collectionId={collection.id} rows={rows} fields={fields}
      pages={pages} collections={collections} api={api} empty={empty}
      openGalleryPage={openGalleryPage} origin={galleryOrigin} />
      : settings.layout === 'timeline' ? <DocsTimeline pages={rows} fields={collection.fields} view={view} open={open} />
      : settings.layout === 'calendar' ? <CalendarView rows={rows} collection={collection} fields={fields}
      dateFieldId={settings.dateFieldId} sorts={settings.sorts} pageMap={pageMap} collectionMap={collectionMap} open={open} />
      : settings.layout === 'board' ? group ? <>
      {!rows.length && <p className="docs-view-empty">{empty}</p>}
      <div className="docs-board-scroll" role="region" aria-label="Colonnes du kanban" tabIndex={0}>
        <div className="docs-board">{groups.map(column => {
          const lane = String(column.value ?? '');
          return <section key={lane} className={'docs-board-lane' + (dragOver === lane ? ' docs-board-target' : '')}
            aria-label={column.label} onDragOver={event => {
              if (editing && !pending && event.dataTransfer.types.includes(boardDragType)) {
                event.preventDefault(); setDragOver(lane);
              }
            }} onDragLeave={event => {
              if (!(event.relatedTarget instanceof Node) || !event.currentTarget.contains(event.relatedTarget)) setDragOver(undefined);
            }} onDrop={event => {
              event.preventDefault();
              setDragOver(undefined);
              const page = rows.find(item => item.id === event.dataTransfer.getData(boardDragType));
              if (page) void move(page, typeof column.value === 'string' ? column.value : null).catch(reason => setError(message(reason)));
            }}>
            <h2>{column.label} <small>{column.pages.length}</small></h2>
            {column.pages.map(page => <article className="docs-board-card" key={page.id} draggable={editing && !pending} onDragStart={event => {
              event.dataTransfer.setData(boardDragType, page.id); event.dataTransfer.effectAllowed = 'move';
            }} onDragEnd={() => setDragOver(undefined)}>
              <DocLink entry={page} open={open} />
              <small>{fieldsSummary(page, group.id)}</small>
              {relationSummary(page)}
              {aggregateSummary(page)}
              {editing && <button className="button subtle" aria-label={'Déplacer ' + page.title} disabled={pending} onClick={() => setMoving(page.id)}>Déplacer</button>}
            </article>)}
            {!column.pages.length && <p className="docs-view-empty">Aucune page.</p>}
          </section>;
        })}</div>
      </div>
    </> : <p className="docs-view-empty">Choisissez une propriété de sélection dans les réglages de la vue.</p>
      : group && rows.length ? groups.filter(item => item.pages.length > 0).map(item => <section className="docs-view-group" key={String(item.value ?? '')}>
        <h2>{item.label} <small>{item.pages.length}</small></h2>{renderRows(item.pages)}
      </section>) : renderRows(rows)}
    {editing && <button className="button subtle docs-add-property" onClick={editing.newField}><Plus size={15} />Propriété</button>}
    {editing && movePage && group && settings.layout === 'board' && <DocsForm title={'Déplacer ' + movePage.title} action="Déplacer"
      close={() => setMoving(undefined)} submit={data => move(movePage, String(data.get('column')) || null)}>
      <label>Nouvelle colonne<select name="column" aria-label="Nouvelle colonne" defaultValue={String(movePage.properties[group.id] ?? '')}>
        {groupOptions(group).map(item => <option key={String(item.value ?? '')} value={String(item.value ?? '')}>{item.label}</option>)}
      </select></label>
    </DocsForm>}
  </>;
}

export function CollectionViews({ collection, view, pages, collections, open, setView, update, saveRelations, newView, editView, deleteView, newPage, schema, newField, readOnly, api, openGalleryPage }: {
  collection: DocCollection; view: DocView; pages: PageSummary[]; collections: CollectionSummary[]; open: OpenDoc; setView: (id: string) => void; update: Update;
  saveRelations: SaveRelations; newView: () => void; editView: () => void; deleteView: () => void; newPage: () => void; schema: () => void; newField: () => void; readOnly: boolean; api: DocsApi; openGalleryPage: OpenGalleryPage;
}) {
  return <>
    <div className="docs-heading">
      <div><span className="docs-heading-icon">{viewSettings(view).layout === 'gallery' ? <Images size={23} aria-hidden /> : <Table size={23} aria-hidden />}</span><h1 id="workspace" tabIndex={-1}>{collection.title}</h1>
        {collection.description && <p>{collection.description}</p>}</div>
    </div>
    <div className="docs-view-controls">
      <div className="docs-row" aria-label="Vues de la collection" role="group">
        {collection.views.map(item => <button key={item.id} className="button" aria-pressed={view.id === item.id}
          onClick={() => setView(item.id)}>{item.name}</button>)}
        {!readOnly && <button className="button subtle" onClick={newView}><Plus size={15} />Vue</button>}
      </div>
      {!readOnly && <div className="docs-row">
        <button className="button" onClick={editView}>Configurer la vue</button>
        <button className="button" onClick={schema}>Propriétés</button>
        {collection.views.length > 1 && <button className="button subtle" onClick={deleteView}>Supprimer la vue</button>}
        <button className="button primary" onClick={newPage}><Plus size={16} />Nouvelle page</button>
      </div>}
    </div>
    <CollectionRows collection={collection} view={view} pages={pages} collections={collections} open={open}
      editing={readOnly ? undefined : { update, saveRelations, newField }} api={api} openGalleryPage={openGalleryPage}
      galleryOrigin={{ kind: 'collection', destinationId: collection.id, viewId: view.id }} />
  </>;
}
