import { expect, type Page } from '@playwright/test';

/**
 * Give historical feature tests an empty, completed workspace through the public
 * API. Full browser onboarding, including the three welcome issues, has its own
 * journeys. No test writes the database or substitutes browser persistence.
 */
export async function createEmptyWorkspace(page: Page, url: string, slug: string) {
  const sessionResponse = await page.request.get(`${url}/api/auth/me`);
  expect(sessionResponse.ok()).toBeTruthy();
  const session = await sessionResponse.json();
  const headers = { 'X-CSRF-Token': session.csrfToken };
  const profile = await page.request.patch(`${url}/api/auth/profile`, {
    headers, data: { displayName: session.user.username, title: '' },
  });
  expect(profile.ok()).toBeTruthy();
  const created = await page.request.post(`${url}/api/workspaces`, {
    headers, data: { name: `Espace ${slug}`, slug, includeWelcomeIssues: false },
  });
  expect(created.status()).toBe(201);
  const { workspace, project } = await created.json();
  const scopedHeaders = { ...headers, 'X-Workspace-Id': String(workspace.id) };
  const completed = await page.request.post(`${url}/api/workspaces/${workspace.id}/onboarding/complete`, {
    headers: scopedHeaders, data: {},
  });
  expect(completed.ok()).toBeTruthy();
  const deleted = await page.request.delete(`${url}/api/projects/${project.id}`, { headers: scopedHeaders });
  expect(deleted.ok()).toBeTruthy();
  return { workspace, headers: scopedHeaders };
}
