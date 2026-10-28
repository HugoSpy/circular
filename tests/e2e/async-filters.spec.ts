import { test, expect } from './fixtures';

test('un déplacement en cours ne restaure pas un ancien filtre projet', async ({ app, page }) => {
  await app.createProject('Projet Alpha', 'ALP');
  await app.createProject('Projet Beta', 'BET');
  await app.createTicket({ title: 'Ticket Alpha', project: 'Projet Alpha', status: 'todo' });
  await app.createTicket({ title: 'Ticket Beta', project: 'Projet Beta', status: 'todo' });
  await app.board();
  await app.projectFilter.selectOption({ label: 'Projet Alpha' });
  await expect(app.card('Ticket Alpha')).toBeVisible();
  await expect(app.card('Ticket Beta')).toHaveCount(0);

  let release!: () => void;
  let notifyStarted!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  const started = new Promise<void>(resolve => { notifyStarted = resolve; });
  await page.route('**/api/issues/*', async route => {
    if (route.request().method() !== 'PATCH') { await route.fallback(); return; }
    notifyStarted();
    await gate;
    await route.fallback();
  });
  try {
    const saved = page.waitForResponse(response => /\/api\/issues\/\d+$/.test(response.url()) && response.request().method() === 'PATCH');
    await app.card('Ticket Alpha').getByRole('combobox', { name: 'Statut de ALP-1', exact: true }).selectOption('done');
    await started;
    await expect(app.card('Ticket Alpha').getByRole('button', { name: 'Ouvrir ALP-1 : Ticket Alpha', exact: true })).toBeDisabled();
    await app.list();
    await expect(app.row('Ticket Alpha')).toBeDisabled();
    await app.board();
    await app.projectFilter.selectOption({ label: 'Projet Beta' });
    await expect(app.card('Ticket Beta')).toBeVisible();
    await expect(app.card('Ticket Alpha')).toHaveCount(0);
    const activeProject = await app.projectFilter.inputValue();
    const refreshed = page.waitForResponse(response => new URL(response.url()).pathname === '/api/issues' && response.request().method() === 'GET');
    release();
    expect((await saved).ok()).toBeTruthy();
    expect(new URL((await refreshed).url()).searchParams.get('projectId')).toBe(activeProject);
    await expect(app.projectFilter).toHaveValue(activeProject);
    await expect(app.card('Ticket Beta')).toBeVisible();
    await expect(app.card('Ticket Alpha')).toHaveCount(0);
  } finally { release(); }
});
