import type { Activity, AuthSession, Comment, Invitation, Issue, IssueInput, IssueTemplate, Label, Project, ProjectInvitation, ProjectMember, SavedView, Settings, TemplateInput } from './types';
let csrfToken: string | undefined;
export function setCsrfToken(value?: string) { csrfToken = value; }
export class ApiError extends Error {
  constructor(message: string, readonly status: number) { super(message); this.name = 'ApiError'; }
}
export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const sessionToken = csrfToken;
  let response: Response;
  try {
    const headers = new Headers(options.headers);
    headers.set('Content-Type', 'application/json');
    if (csrfToken && options.method && !['GET', 'HEAD', 'OPTIONS'].includes(options.method.toUpperCase())) headers.set('X-CSRF-Token', csrfToken);
    response = await fetch(`/api${path}`, { ...options, credentials: 'same-origin', headers });
  } catch {
    throw new Error('Serveur injoignable. Vérifiez que le backend est démarré, puis réessayez.');
  }
  if (response.status === 204) return undefined as T;
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(response.ok ? 'Réponse du serveur invalide. Réessayez.' : `Le serveur ne répond pas correctement (${response.status}). Votre saisie est conservée.`);
  }
  if (!response.ok) {
    if (response.status === 401 && sessionToken === csrfToken && !['/auth/me', '/auth/login', '/auth/register'].includes(path)) window.dispatchEvent(new Event('circular:session-expired'));
    throw new ApiError(data.error || 'Une erreur est survenue. Réessayez.', response.status);
  }
  return data as T;
}
export const api = {
  me: () => request<AuthSession>('/auth/me'),
  login: (identifier: string, password: string) => request<AuthSession>('/auth/login', { method: 'POST', body: JSON.stringify({ identifier, password }) }),
  register: (username: string, email: string, password: string) => request<AuthSession>('/auth/register', { method: 'POST', body: JSON.stringify({ username, email, password }) }),
  logout: () => request<void>('/auth/logout', { method: 'POST', body: '{}' }),
  changePassword: (currentPassword: string, newPassword: string) => request<void>('/auth/password', { method: 'POST', body: JSON.stringify({ currentPassword, newPassword }) }),
  invitations: () => request<Invitation[]>('/invitations'),
  acceptInvitation: (id: number) => request<void>(`/invitations/${id}/accept`, { method: 'POST', body: '{}' }),
  declineInvitation: (id: number) => request<void>(`/invitations/${id}/decline`, { method: 'POST', body: '{}' }),
  members: (id: number) => request<ProjectMember[]>(`/projects/${id}/members`),
  projectInvitations: (id: number) => request<ProjectInvitation[]>(`/projects/${id}/invitations`),
  invite: (id: number, email: string) => request<ProjectInvitation>(`/projects/${id}/invitations`, { method: 'POST', body: JSON.stringify({ email }) }),
  removeMember: (id: number, userId: number) => request<void>(`/projects/${id}/members/${userId}`, { method: 'DELETE' }),
  cancelInvitation: (id: number, invitationId: number) => request<void>(`/projects/${id}/invitations/${invitationId}`, { method: 'DELETE' }),
  projects: () => request<Project[]>('/projects'),
  createProject: (data: Pick<Project, 'name'|'key'|'description'|'color'> & Partial<Pick<Project, 'status'|'dueDate'>>) => request<Project>('/projects', { method: 'POST', body: JSON.stringify(data) }),
  updateProject: (id: number, data: Partial<Pick<Project, 'name'|'description'|'color'|'status'|'dueDate'>>) => request<Project>(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteProject: (id: number) => request<void>(`/projects/${id}`, { method: 'DELETE' }),
  issues: (query = '') => request<Issue[]>(`/issues${query ? `?${query}` : ''}`),
  issue: (id: number) => request<Issue>(`/issues/${id}`),
  createIssue: (data: IssueInput) => request<Issue>('/issues', { method: 'POST', body: JSON.stringify(data) }),
  updateIssue: (id: number, data: Partial<IssueInput>) => request<Issue>(`/issues/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteIssue: (id: number) => request<void>(`/issues/${id}`, { method: 'DELETE' }),
  labels: () => request<Label[]>('/labels'),
  createLabel: (name: string, color = '#F2CF63', description = '') => request<Label>('/labels', { method: 'POST', body: JSON.stringify({ name, color, description }) }),
  updateLabel: (id: number, data: Partial<Pick<Label, 'name'|'color'|'description'>>) => request<Label>(`/labels/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteLabel: (id: number) => request<void>(`/labels/${id}`, { method: 'DELETE' }),
  comments: (id: number) => request<Comment[]>(`/issues/${id}/comments`),
  addComment: (id: number, body: string) => request<Comment>(`/issues/${id}/comments`, { method: 'POST', body: JSON.stringify({ body }) }),
  updateComment: (id: number, commentId: number, body: string) => request<Comment>(`/issues/${id}/comments/${commentId}`, { method: 'PATCH', body: JSON.stringify({ body }) }),
  deleteComment: (id: number, commentId: number) => request<void>(`/issues/${id}/comments/${commentId}`, { method: 'DELETE' }),
  activity: (id: number) => request<Activity[]>(`/issues/${id}/activity`),
  duplicateIssue: (id: number) => request<Issue>(`/issues/${id}/duplicate`, { method: 'POST' }),
  settings: () => request<Settings>('/settings'),
  updateSettings: (data: Partial<Settings>) => request<Settings>('/settings', { method: 'PATCH', body: JSON.stringify(data) }),
  views: () => request<SavedView[]>('/views'),
  createView: (data: Omit<SavedView, 'id'>) => request<SavedView>('/views', { method: 'POST', body: JSON.stringify(data) }),
  updateView: (id: number, data: Partial<Omit<SavedView, 'id'>>) => request<SavedView>(`/views/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteView: (id: number) => request<void>(`/views/${id}`, { method: 'DELETE' }),
  templates: () => request<IssueTemplate[]>('/templates'),
  createTemplate: (data: TemplateInput) => request<IssueTemplate>('/templates', { method: 'POST', body: JSON.stringify(data) }),
  updateTemplate: (id: number, data: Partial<TemplateInput>) => request<IssueTemplate>(`/templates/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteTemplate: (id: number) => request<void>(`/templates/${id}`, { method: 'DELETE' }),
};
