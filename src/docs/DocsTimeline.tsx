import { useId, useState } from 'react';
import { DocLink } from './DocsLink';
import type { DocView, OpenDoc, PageSummary, PropertyField } from './api';
import { viewSettings } from './collection-views';

const dayMs = 86_400_000;
const calendarDate = (year: number, month: number, day: number) => {
  const date = new Date(0);
  date.setUTCFullYear(year, month, day);
  date.setUTCHours(0, 0, 0, 0);
  return date;
};
const dateNumber = (value: unknown) => {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const [year, month, day] = value.split('-').map(Number);
  const date = calendarDate(year, month - 1, day).getTime();
  return new Date(date).toISOString().slice(0, 10) === value ? date : null;
};

export function DocsTimeline({ pages, fields, view, open }: {
  pages: PageSummary[]; fields: PropertyField[]; view: DocView; open: OpenDoc;
}) {
  const settings = viewSettings(view);
  const undatedTitleId = useId();
  const invalidTitleId = useId();
  const startField = fields.find(field => field.id === settings.dateFieldId && field.kind === 'date');
  const endField = fields.find(field => field.id === settings.endDateFieldId && field.kind === 'date');
  const [month, setMonth] = useState(() => {
    const today = new Date();
    return calendarDate(today.getFullYear(), today.getMonth(), 1);
  });
  if (!startField || !endField || startField.id === endField.id) {
    return <p className="docs-view-empty">Cette chronologie doit utiliser deux propriétés Date distinctes.</p>;
  }
  const first = month.getTime();
  const last = calendarDate(month.getUTCFullYear(), month.getUTCMonth() + 1, 0).getTime();
  const dayCount = (last - first) / dayMs + 1;
  const monthLabel = new Intl.DateTimeFormat('fr-FR', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(month);
  const prepared = pages.map(page => ({ page, start: dateNumber(page.properties[startField.id]), end: dateNumber(page.properties[endField.id]) }));
  const undated = prepared.filter(item => item.start === null && item.end === null);
  const invalid = prepared.filter(item => item.start !== null && item.end !== null && item.end < item.start);
  const dated = prepared.filter(item => item.start !== null || item.end !== null)
    .filter(item => !(item.start !== null && item.end !== null && item.end < item.start));
  const visible = dated.filter(item => {
    const start = item.start ?? item.end!;
    const end = item.end ?? item.start!;
    return start <= last && end >= first;
  });
  const labelDate = new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
  const displayDates = (start: number | null, end: number | null) => start === null && end === null ? 'Sans date'
    : start === null ? 'Jalon · ' + labelDate.format(end!) : end === null ? 'Jalon · ' + labelDate.format(start)
      : labelDate.format(start) + ' → ' + labelDate.format(end);
  const renderRow = (item: typeof prepared[number], mobile = false) => {
    const start = item.start ?? item.end!;
    const end = item.end ?? item.start!;
    const clippedStart = Math.max(start, first);
    const clippedEnd = Math.min(end, last);
    const single = item.start === null || item.end === null;
    const firstDay = Math.floor((clippedStart - first) / dayMs) + 1;
    const span = Math.floor((clippedEnd - clippedStart) / dayMs) + 1;
    const contents = <>
      <div className="docs-timeline-page"><DocLink entry={item.page} open={open} /><small>{displayDates(item.start, item.end)}</small></div>
      {!mobile && <div className="docs-timeline-track" aria-hidden="true" style={{ '--days': dayCount } as React.CSSProperties}>
        <span className={single ? 'docs-timeline-milestone' : 'docs-timeline-bar'} style={{
          '--first': firstDay, '--length': span,
        } as React.CSSProperties}>
          {item.start !== null && item.start < first && <i className="docs-timeline-overflow-start">‹</i>}
          {item.end !== null && item.end > last && <i className="docs-timeline-overflow-end">›</i>}
        </span>
      </div>}
    </>;
    return mobile ? <li className="docs-timeline-mobile-row" key={item.page.id}>{contents}</li>
      : <div className="docs-timeline-row" key={item.page.id}>{contents}</div>;
  };
  const moveMonth = (delta: number) => setMonth(value => calendarDate(value.getUTCFullYear(), value.getUTCMonth() + delta, 1));

  return <section className="docs-timeline" aria-label="Chronologie du mois">
    <header className="docs-timeline-header">
      <span className="docs-timeline-property">{startField.name} → {endField.name}</span>
      <h2 aria-live="polite">{monthLabel}</h2>
      <div className="docs-row">
        <button type="button" className="button" aria-label="Mois précédent" onClick={() => moveMonth(-1)}>←</button>
        <button type="button" className="button" onClick={() => {
          const current = new Date(); setMonth(calendarDate(current.getFullYear(), current.getMonth(), 1));
        }}>Aujourd’hui</button>
        <button type="button" className="button" aria-label="Mois suivant" onClick={() => moveMonth(1)}>→</button>
      </div>
    </header>
    <div className="docs-timeline-axis" aria-hidden="true">
      <span>Page</span><div className="docs-timeline-days" style={{ '--days': dayCount } as React.CSSProperties}>
        {Array.from({ length: dayCount }, (_, index) => <span key={index}>{index === 0 || index === dayCount - 1 || (index + 1) % 7 === 1 ? index + 1 : ''}</span>)}
      </div>
    </div>
    <div className="docs-timeline-rows">{visible.map(item => renderRow(item))}</div>
    <ul className="docs-timeline-mobile">{visible.map(item => renderRow(item, true))}</ul>
    {!visible.length && <p className="docs-view-empty">{pages.length === 0 && settings.filterTree.conditions.length > 0
      ? 'Aucune page ne correspond aux filtres.' : 'Aucune page planifiée ce mois-ci.'}</p>}
    <section className="docs-timeline-extra" aria-labelledby={undatedTitleId}>
      <h3 id={undatedTitleId}>Sans date</h3><small>{undated.length}</small>
      {undated.length ? <ul>{undated.map(item => <li key={item.page.id}><DocLink entry={item.page} open={open} /></li>)}</ul> : <p>Aucune page sans date.</p>}
    </section>
    {invalid.length > 0 && <section className="docs-timeline-extra is-invalid" aria-labelledby={invalidTitleId}>
      <h3 id={invalidTitleId}>Dates à corriger</h3><small>{invalid.length}</small>
      <ul>{invalid.map(item => <li key={item.page.id}><DocLink entry={item.page} open={open} /><small>{displayDates(item.start, item.end)} · La fin précède le début.</small></li>)}</ul>
    </section>}
  </section>;
}
