import { test, expect } from './fixtures';

test('une sauvegarde et sa reprise conservent les préférences modifiées ailleurs', async ({ app, page, server }) => {
  await app.createProject('Persistance des réglages', 'REG');
  await app.createTicket({ title: 'Conserver les préférences', priority: 'high' });
  await expect(page.getByText('Réglages enregistrés', { exact: true })).toBeVisible();

  // Simulate a second tab changing an unrelated preference after this tab loaded.
  expect((await page.request.patch(`${server.url}/api/settings`, { data: { commentSubmit: 'enter' } })).ok()).toBeTruthy();
  const savedFilter = page.waitForResponse(response => response.url().endsWith('/api/settings') && response.request().method() === 'PATCH');
  await app.search.fill('Conserver');
  expect((await savedFilter).ok()).toBeTruthy();
  await expect(page.getByText('Réglages enregistrés', { exact: true })).toBeVisible();
  expect(await (await page.request.get(`${server.url}/api/settings`)).json()).toMatchObject({ commentSubmit: 'enter', filters: { q: 'Conserver' } });

  await page.route('**/api/settings', route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: 'Interruption temporaire simulée.' }) }), { times: 1 });
  await app.priorityFilter.selectOption('high');
  await expect(page.getByRole('alert').filter({ hasText: 'Réglages non enregistrés' })).toBeVisible();
  await expect(app.priorityFilter).toHaveValue('high');
  expect((await page.request.patch(`${server.url}/api/settings`, { data: { fontSize: 'large' } })).ok()).toBeTruthy();

  const retried = page.waitForResponse(response => response.url().endsWith('/api/settings') && response.request().method() === 'PATCH');
  await page.getByRole('button', { name: 'Réessayer l’enregistrement des réglages', exact: true }).click();
  expect((await retried).ok()).toBeTruthy();
  await expect(page.getByText('Réglages enregistrés', { exact: true })).toBeVisible();
  expect(await (await page.request.get(`${server.url}/api/settings`)).json()).toMatchObject({ commentSubmit: 'enter', fontSize: 'large', filters: { q: 'Conserver', priority: 'high' } });
  await server.restart();
  await page.reload();
  await expect(app.search).toHaveValue('Conserver');
  await expect(app.priorityFilter).toHaveValue('high');
  await expect(page.locator('html')).toHaveAttribute('data-font-size', 'large');
  await app.openTicket('Conserver les préférences');
  await expect(app.detail.getByText('Entrée pour publier · Maj + Entrée pour une nouvelle ligne', { exact: true })).toBeVisible();
});
