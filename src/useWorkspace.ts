import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api';
import { DEFAULT_DISPLAY, type DisplaySettings, type Filters, type Issue, type IssueTemplate, type Label, type Project, type SavedView } from './types';
import { message } from './ui';

export type { Filters } from './types';
export { EMPTY_FILTERS } from './types';
export function useWorkspace(filters: Filters, display: DisplaySettings = DEFAULT_DISPLAY, enabled = true) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [labels, setLabels] = useState<Label[]>([]);
  const [templates, setTemplates] = useState<IssueTemplate[]>([]);
  const [views, setViews] = useState<SavedView[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState(filters.q);
  const requestId = useRef(0);
  useEffect(() => { const timeout = setTimeout(() => setQuery(filters.q), 180); return () => clearTimeout(timeout); }, [filters.q]);
  const refresh = useCallback(async () => {
    if (!enabled) return;
    const sequence = ++requestId.current;
    setLoading(true);
    const params = new URLSearchParams();
    if (query.trim()) params.set('q', query.trim());
    if (filters.projectId) params.set('projectId', filters.projectId);
    if (filters.status) params.set('status', filters.status);
    if (filters.priority) params.set('priority', filters.priority);
    if (filters.statuses.length) params.set('statuses', filters.statuses.join(','));
    if (filters.priorities.length) params.set('priorities', filters.priorities.join(','));
    if (filters.labelIds.length) params.set('labelIds', filters.labelIds.join(','));
    if (filters.favoritesOnly) params.set('favoritesOnly', 'true');
    params.set('sortBy', display.sortBy);
    params.set('direction', display.direction);
    try {
      const [nextProjects, nextIssues, nextLabels, nextTemplates, nextViews] = await Promise.all([api.projects(), api.issues(params.toString()), api.labels(), api.templates(), api.views()]);
      if (sequence === requestId.current) { setProjects(nextProjects); setIssues(nextIssues); setLabels(nextLabels); setTemplates(nextTemplates); setViews(nextViews); setError(''); }
    } catch (error) { if (sequence === requestId.current) setError(message(error)); }
    finally { if (sequence === requestId.current) setLoading(false); }
  }, [query, filters.projectId, filters.status, filters.priority, filters.statuses, filters.priorities, filters.labelIds, filters.favoritesOnly, display.sortBy, display.direction, enabled]);
  useEffect(() => { void refresh(); return () => { requestId.current++; }; }, [refresh]);
  const latestRefresh = useRef(refresh);
  latestRefresh.current = refresh;
  const reload = useCallback(() => latestRefresh.current(), []);
  const addLabel = (label: Label) => setLabels(current => [...current.filter(item => item.id !== label.id), label].sort((a, b) => a.name.localeCompare(b.name, 'fr')));
  return { projects, issues, labels, templates, views, error, loading, refresh: reload, addLabel };
}
