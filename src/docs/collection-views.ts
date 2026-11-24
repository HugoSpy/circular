import { calculationErrors, type AggregateError, type DocView, type FilterRule, type FilterTree, type Layout, type PageSummary, type PropertyField, type PropertyKind, type PropertyValue, type ViewInput } from './api';

export const layoutLabels: Record<Layout, string> = { table: 'Table', list: 'Liste', board: 'Kanban', calendar: 'Calendrier', timeline: 'Chronologie', gallery: 'Galerie' };
export const layoutChoices = Object.entries(layoutLabels) as [Layout, string][];
export const emptyTree: FilterTree = { mode: 'all', conditions: [] };

export function viewSettings(view?: DocView): ViewInput {
  if (!view) return { name: '', layout: 'table', groupBy: null, dateFieldId: null, endDateFieldId: null, filterTree: emptyTree, sorts: [], hidden: [] };
  if ('layout' in view) return { ...view, dateFieldId: view.dateFieldId ?? null, endDateFieldId: view.endDateFieldId ?? null };
  return {
    name: view.name, layout: 'table', groupBy: null, dateFieldId: null, endDateFieldId: null, hidden: view.hidden,
    filterTree: { mode: 'all', conditions: view.filters.map(rule => ({ ...rule, operator: 'eq' })) },
    sorts: [{ fieldId: view.sortBy, direction: view.direction }],
  };
}

const text = (value: unknown) => String(value ?? '').normalize('NFD').replace(/\p{M}/gu, '').toLocaleLowerCase('fr');

export function isAggregateError(value: PropertyValue | AggregateError): value is AggregateError {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function valueRank(value: PropertyValue | AggregateError) {
  return isAggregateError(value) ? 2 : value === null ? 1 : 0;
}

function matches(page: PageSummary, rule: FilterRule) {
  const actual = page.properties[rule.fieldId] ?? null;
  if (isAggregateError(actual)) return false;
  const value = rule.value;
  const empty = actual === null || actual === '' || (Array.isArray(actual) && !actual.length);
  if (rule.operator === 'eq') return actual === value;
  if (rule.operator === 'empty') return empty;
  if (rule.operator === 'filled') return !empty;
  if (actual === null || value === null) return false;
  if (rule.operator === 'contains') return Array.isArray(actual) ? actual.includes(String(value)) : text(actual).includes(text(value));
  const comparison = typeof actual === 'number' && typeof value === 'number' ? actual - value : String(actual).localeCompare(String(value), 'fr');
  return rule.operator === 'gte' ? comparison >= 0 : comparison <= 0;
}

function matchesTree(page: PageSummary, tree: FilterTree): boolean {
  if (!tree.conditions.length) return true;
  const evaluate = (item: FilterTree['conditions'][number]) => 'conditions' in item
    ? matchesTree(page, item) : matches(page, item);
  return tree.mode === 'all' ? tree.conditions.every(evaluate) : tree.conditions.some(evaluate);
}

export function compareViewRows(left: PageSummary, right: PageSummary, sorts: ViewInput['sorts']) {
  for (const { fieldId, direction } of sorts) {
    const a = fieldId === 'title' ? left.title : left.properties[fieldId] ?? null;
    const b = fieldId === 'title' ? right.title : right.properties[fieldId] ?? null;
    const rank = valueRank(a) - valueRank(b);
    if (rank) return rank;
    if (a === null || isAggregateError(a)) continue;
    const difference = typeof a === 'number' && typeof b === 'number' ? a - b : String(a).localeCompare(String(b), 'fr');
    if (difference) return difference * (direction === 'desc' ? -1 : 1);
  }
  return 0;
}

export function viewRows(pages: PageSummary[], collectionId: string, view: ViewInput) {
  const rows = pages.filter(page => page.collectionId === collectionId && matchesTree(page, view.filterTree));
  return rows.sort((left, right) => compareViewRows(left, right, view.sorts) || left.id.localeCompare(right.id));
}

export function groupOptions(field: PropertyField): { value: string | boolean | null; label: string }[] {
  const options = field.kind === 'checkbox'
    ? [{ value: true, label: 'Cochée' }, { value: false, label: 'Décochée' }]
    : field.options.map(option => ({ value: option, label: option }));
  return [...options, { value: null, label: 'Sans valeur' }];
}

export function supportsGrouping(kind: PropertyKind, layout: Layout) {
  return layout !== 'calendar' && layout !== 'timeline' && layout !== 'gallery' && (kind === 'select' || (layout !== 'board' && kind === 'checkbox'));
}

export function valueLabel(value: PropertyValue | AggregateError) {
  if (isAggregateError(value)) return calculationErrors[value.error];
  if (Array.isArray(value)) return value.join(' · ');
  if (typeof value === 'boolean') return value ? 'Cochée' : 'Décochée';
  return value == null ? '' : String(value);
}
