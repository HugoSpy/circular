import type { Activity, AuthSession, Comment, IncomingWorkspaceInvitation, Invitation, Issue, IssueInput, IssueTemplate, Label, Project, ProjectInvitation, ProjectMember, SavedView, Settings, TemplateInput, User, Workspace, WorkspaceInvitation, WorkspaceInviteLink, WorkspaceMember } from './types';
let csrfToken: string | undefined;
let sessionGeneration = 0;
let activeWorkspaceId: number | undefined;
let workspaceVersion = 0;
export function setCsrfToken(value?: string) { if (csrfToken !== value) { csrfToken = value; sessionGeneration++; } }
export function getSessionGeneration() { return sessionGeneration; }
export function setWorkspaceId(value?: number) { if (activeWorkspaceId !== value) { activeWorkspaceId = value; workspaceVersion++; } }
export function getWorkspaceId() { return activeWorkspaceId; }
export class ApiError extends Error {
  constructor(message: string, readonly status: number) { super(message); this.name = 'ApiError'; }
}
export async function request<T>(path: string, options: RequestInit = {}, scope: number | null | undefined = activeWorkspaceId): Promise<T> {
  const sessionToken = csrfToken;
  const sessionVersion = sessionGeneration;
  const version = workspaceVersion;
  let response: Response;
  try {
    const headers = new Headers(options.headers);
    headers.set('Content-Type', 'application/json');
    if (scope != null) headers.set('X-Workspace-Id', String(scope));
    if (csrfToken && options.method && !['GET', 'HEAD', 'OPTIONS'].includes(options.method.toUpperCase())) headers.set('X-CSRF-Token', csrfToken);
    response = await fetch(`/api${path}`, { ...options, credentials: 'same-origin', headers });
  } catch {
    throw new Error('Serveur injoignable. Vérifiez que le backend est démarré, puis réessayez.');
  }
  if (sessionVersion !== sessionGeneration) throw new ApiError('La session a changé. La réponse précédente a été ignorée.', 409);
  if (scope != null && (scope !== activeWorkspaceId || version !== workspaceVersion)) throw new ApiError('L’espace actif a changé. La réponse précédente a été ignorée.', 409);
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
  me: () => request<AuthSession>('/auth/me', {}, null),
  login: (identifier: string, password: string) => request<AuthSession>('/auth/login', { method: 'POST', body: JSON.stringify({ identifier, password }) }, null),
  register: (username: string, email: string, password: string) => request<AuthSession>('/auth/register', { method: 'POST', body: JSON.stringify({ username, email, password }) }, null),
  logout: () => request<void>('/auth/logout', { method: 'POST', body: '{}' }, null),
  changePassword: (currentPassword: string, newPassword: string) => request<void>('/auth/password', { method: 'POST', body: JSON.stringify({ currentPassword, newPassword }) }, null),
  updateProfile: (data: Pick<User, 'displayName'|'title'>) => request<User>('/auth/profile', { method: 'PATCH', body: JSON.stringify(data) }, null),
  workspaces: () => request<Workspace[]>('/workspaces', {}, null),
  createWorkspace: (data: { name: string; slug: string }) => request<{ workspace: Workspace; project: Project }>('/workspaces', { method: 'POST', body: JSON.stringify(data) }, null),
  updateWorkspace: (id: number, data: { name: string; slug: string }) => request<Workspace>(`/workspaces/${id}`, { method: 'PATCH', body: JSON.stringify(data) }, null),
  finishOnboarding: (id: number) => request<Workspace>(`/workspaces/${id}/onboarding/complete`, { method: 'POST', body: '{}' }, null),
  workspaceMembers: (id: number) => request<WorkspaceMember[]>(`/workspaces/${id}/members`, {}, null),
  removeWorkspaceMember: (id: number, userId: number) => request<void>(`/workspaces/${id}/members/${userId}`, { method: 'DELETE' }, null),
  workspaceInvitations: (id: number) => request<WorkspaceInvitation[]>(`/workspaces/${id}/invitations`, {}, null),
  inviteToWorkspace: (id: number, email: string) => request<WorkspaceInvitation>(`/workspaces/${id}/invitations`, { method: 'POST', body: JSON.stringify({ email }) }, null),
  cancelWorkspaceInvitation: (id: number, invitationId: number) => request<void>(`/workspaces/${id}/invitations/${invitationId}`, { method: 'DELETE' }, null),
  workspaceInbox: () => request<IncomingWorkspaceInvitation[]>('/workspace-invitations', {}, null),
  acceptWorkspaceInvitation: (id: number) => request<Workspace>(`/workspace-invitations/${id}/accept`, { method: 'POST', body: '{}' }, null),
  declineWorkspaceInvitation: (id: number) => request<void>(`/workspace-invitations/${id}/decline`, { method: 'POST', body: '{}' }, null),
  workspaceInviteLinks: (id: number) => request<WorkspaceInviteLink[]>(`/workspaces/${id}/invite-links`, {}, null),
  createWorkspaceInviteLink: (id: number) => request<WorkspaceInviteLink>(`/workspaces/${id}/invite-links`, { method: 'POST', body: '{}' }, null),
  revokeWorkspaceInviteLink: (id: number, linkId: number) => request<void>(`/workspaces/${id}/invite-links/${linkId}`, { method: 'DELETE' }, null),
  previewWorkspaceLink: (token: string) => request<{ workspaceName: string; workspaceSlug: string; expiresAt: string }>('/workspace-invite-links/preview', { method: 'POST', body: JSON.stringify({ token }) }, null),
  acceptWorkspaceLink: (token: string) => request<Workspace>('/workspace-invite-links/accept', { method: 'POST', body: JSON.stringify({ token }) }, null),
  invitations: () => request<Invitation[]>('/invitations', {}, null),
  acceptInvitation: (id: number) => request<void>(`/invitations/${id}/accept`, { method: 'POST', body: '{}' }, null),
  declineInvitation: (id: number) => request<void>(`/invitations/${id}/decline`, { method: 'POST', body: '{}' }, null),
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
  settings: (scope = activeWorkspaceId) => request<Settings>('/settings', {}, scope),
  updateSettings: (data: Partial<Settings>, scope = activeWorkspaceId) => request<Settings>('/settings', { method: 'PATCH', body: JSON.stringify(data) }, scope),
  views: () => request<SavedView[]>('/views'),
  createView: (data: Omit<SavedView, 'id'>) => request<SavedView>('/views', { method: 'POST', body: JSON.stringify(data) }),
  updateView: (id: number, data: Partial<Omit<SavedView, 'id'>>) => request<SavedView>(`/views/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteView: (id: number) => request<void>(`/views/${id}`, { method: 'DELETE' }),
  templates: () => request<IssueTemplate[]>('/templates'),
  createTemplate: (data: TemplateInput) => request<IssueTemplate>('/templates', { method: 'POST', body: JSON.stringify(data) }),
  updateTemplate: (id: number, data: Partial<TemplateInput>) => request<IssueTemplate>(`/templates/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteTemplate: (id: number) => request<void>(`/templates/${id}`, { method: 'DELETE' }),
};
