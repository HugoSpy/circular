export const STATUSES = ['backlog', 'todo', 'in_progress', 'in_review', 'done'] as const;
export type Status = typeof STATUSES[number];
export const STATUS_NAMES: Record<Status, string> = { backlog: 'À trier', todo: 'À faire', in_progress: 'En cours', in_review: 'En revue', done: 'Terminé' };
export const PRIORITIES = ['none', 'low', 'medium', 'high', 'urgent'] as const;
export type Priority = typeof PRIORITIES[number];
export const PRIORITY_NAMES: Record<Priority, string> = { none: 'Aucune', low: 'Basse', medium: 'Moyenne', high: 'Haute', urgent: 'Urgente' };
export const PROJECT_STATUSES = ['backlog', 'planned', 'in_progress', 'completed', 'canceled'] as const;
export type ProjectStatus = typeof PROJECT_STATUSES[number];
export const PROJECT_STATUS_NAMES: Record<ProjectStatus, string> = { backlog: 'À étudier', planned: 'Planifié', in_progress: 'En cours', completed: 'Terminé', canceled: 'Annulé' };
export interface User { id: number; email: string; username: string; }
export interface AuthSession { user: User; csrfToken: string; }
export interface Project { id: number; name: string; key: string; description: string; color: string; issueCount: number; doneCount: number; createdAt: string; status: ProjectStatus; dueDate: string | null; role: 'owner'|'member'; }
export interface ProjectMember extends User { role: 'owner'|'member'; }
export interface ProjectInvitation { id: number; email: string; username: string; createdAt: string; }
export interface Invitation { id: number; projectId: number; projectName: string; inviterName: string; createdAt: string; }
export interface Label { id: number; name: string; color: string; description: string; canEdit: boolean; }
export interface Issue { id: number; identifier: string; title: string; description: string; projectId: number; status: Status; priority: Priority; labels: Label[]; createdAt: string; updatedAt: string; dueDate: string | null; isFavorite: boolean; }
export interface Comment { id: number; issueId: number; body: string; createdAt: string; author: Pick<User, 'id'|'username'> | null; canEdit: boolean; canDelete: boolean; }
export type IssueInput = Pick<Issue, 'title'|'description'|'projectId'|'status'|'priority'> & { labelIds: number[]; dueDate?: string | null; isFavorite?: boolean };
export interface Filters { q: string; projectId: string; status: '' | Status; priority: '' | Priority; labelIds: number[]; statuses: Status[]; priorities: Priority[]; favoritesOnly: boolean; }
export type DisplayProperty = 'identifier'|'status'|'priority'|'project'|'labels'|'createdAt'|'updatedAt'|'dueDate';
export interface DisplaySettings { view: 'list'|'board'; grouping: 'status'|'project'|'priority'|'none'; sortBy: 'createdAt'|'updatedAt'|'title'|'priority'|'dueDate'; direction: 'asc'|'desc'; properties: DisplayProperty[]; showEmptyGroups: boolean; collapsedGroups: string[]; hiddenStatuses: Status[]; }
export interface Settings { homeView: 'resume'|'list'|'board'|'projects'; fontSize: 'small'|'default'|'large'; density: 'compact'|'comfortable'; reduceMotion: boolean; commentSubmit: 'ctrl_enter'|'enter'; display: DisplaySettings; filters: Filters; }
export interface SavedView { id: number; name: string; filters: Filters; display: DisplaySettings; }
export interface IssueTemplate { id: number; name: string; title: string; description: string; projectId: number | null; status: Status; priority: Priority; labelIds: number[]; }
export type TemplateInput = Omit<IssueTemplate, 'id'>;
export interface Activity { id: number; issueId: number; kind: string; body: string; createdAt: string; actor: Pick<User, 'id'|'username'> | null; }
export const EMPTY_FILTERS: Filters = { q: '', projectId: '', status: '', priority: '', labelIds: [], statuses: [], priorities: [], favoritesOnly: false };
export const DEFAULT_DISPLAY: DisplaySettings = { view: 'list', grouping: 'status', sortBy: 'createdAt', direction: 'desc', properties: ['identifier', 'status', 'priority', 'project', 'labels'], showEmptyGroups: false, collapsedGroups: [], hiddenStatuses: [] };
export const DEFAULT_SETTINGS: Settings = { homeView: 'resume', fontSize: 'default', density: 'compact', reduceMotion: false, commentSubmit: 'ctrl_enter', display: DEFAULT_DISPLAY, filters: EMPTY_FILTERS };
export function hasFilters(filters: Filters) { return Boolean(filters.q || filters.projectId || filters.status || filters.priority || filters.labelIds.length || filters.statuses.length || filters.priorities.length || filters.favoritesOnly); }
