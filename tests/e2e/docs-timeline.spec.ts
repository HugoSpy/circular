import { expect, test } from './fixtures';

test.use({ timezoneId: 'America/Los_Angeles' });

async function create(page: import('@playwright/test').Page, url: string, data: object) {
  const response = await page.request.post(url, { data });
  expect(response.status()).toBe(201);
  return response.json();
}

test('la chronologie découpe les plages, distingue les jalons et reste cohérente dans une vue intégrée', async ({ page, app }) => {
  await page.clock.install({ time: new Date('2026-11-24T18:00:00Z') });
  await app.page.getByRole('button', { name: 'Docs', exact: true }).click();
  const main = page.getByRole('main');
  const exportHref = await main.getByRole('link', { name: 'Exporter', exact: true }).getAttribute('href');
  const base = new URL(exportHref!, page.url()).href.replace(/\/export$/, '');
  const collection = await create(page, base + '/collections', { title: 'Planning Chronologie' });
  const collectionUrl = base + '/collections/' + collection.id;
  const start = await create(page, collectionUrl + '/fields', { name: 'Début prévu', kind: 'date' });
  const end = await create(page, collectionUrl + '/fields', { name: 'Fin prévue', kind: 'date' });
  const state = await create(page, collectionUrl + '/fields', { name: 'État', kind: 'select', options: ['En cours', 'À faire', 'Terminé'] });
  const pages = await Promise.all(['Traversée', 'Jalon début', 'Jalon fin', 'Même jour', 'Fin après mois', 'Année traversée', 'Sans dates', 'Dates inversées', 'Exclue', 'Corbeille'].map(title =>
    create(page, base + '/pages', { title, collectionId: collection.id })));
  const [range, startMilestone, endMilestone, sameDay, trailingOnly, acrossYear, undated, reversed, excluded, trashed] = pages;
  const set = async (entry: { id: string }, field: { id: string }, value: string) => {
    expect((await page.request.patch(base + '/pages/' + entry.id + '/properties/' + field.id, { data: { value } })).ok()).toBeTruthy();
  };
  await set(range, start, '2026-10-28'); await set(range, end, '2026-11-07'); await set(range, state, 'En cours');
  await set(startMilestone, start, '2026-11-12'); await set(startMilestone, state, 'En cours');
  await set(endMilestone, end, '2026-11-14'); await set(endMilestone, state, 'En cours');
  await set(sameDay, start, '2026-11-16'); await set(sameDay, end, '2026-11-16'); await set(sameDay, state, 'En cours');
  await set(trailingOnly, start, '2026-11-27'); await set(trailingOnly, end, '2026-12-04'); await set(trailingOnly, state, 'En cours');
  await set(acrossYear, start, '2026-12-29'); await set(acrossYear, end, '2027-01-03'); await set(acrossYear, state, 'En cours');
  await set(undated, state, 'En cours');
  await set(reversed, start, '2026-11-23'); await set(reversed, end, '2026-11-20'); await set(reversed, state, 'En cours');
  await set(excluded, start, '2026-11-05'); await set(excluded, end, '2026-11-09'); await set(excluded, state, 'À faire');
  await set(trashed, start, '2026-11-15'); await set(trashed, end, '2026-11-17'); await set(trashed, state, 'En cours');
  const trashRevision = await (await page.request.get(base + '/pages/' + trashed.id)).json();
  const trashResponse = await page.request.post(base + '/pages/' + trashed.id + '/trash', { data: { revision: trashRevision.revision } });
  expect(trashResponse.status()).toBe(201);
  const trashOperation = await trashResponse.json();

  const address = new URL(page.url());
  address.searchParams.set('docs', collection.id);
  await page.goto(address.href);
  const mainButton = (name: string) => main.getByRole('button', { name, exact: true });
  const dialog = page.getByRole('dialog');
  await mainButton('Vue').click();
  await dialog.getByRole('textbox', { name: 'Nom de la vue', exact: true }).fill('Chronologie équipe');
  await dialog.getByRole('combobox', { name: 'Présentation', exact: true }).selectOption('timeline');
  await dialog.getByRole('combobox', { name: 'Propriété de début', exact: true }).selectOption(start.id);
  await dialog.getByRole('combobox', { name: 'Propriété de fin', exact: true }).selectOption(end.id);
  await dialog.getByRole('button', { name: 'Ajouter un filtre', exact: true }).click();
  await dialog.getByRole('combobox', { name: 'Propriété du filtre', exact: true }).selectOption(state.id);
  await dialog.getByRole('combobox', { name: 'Est égal à', exact: true }).selectOption('En cours');
  await dialog.getByRole('button', { name: 'Ajouter un tri', exact: true }).click();
  await dialog.getByRole('combobox', { name: 'Propriété du tri 1', exact: true }).selectOption('title');
  await dialog.getByRole('combobox', { name: 'Ordre du tri 1', exact: true }).selectOption('asc');
  await dialog.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(main.getByRole('region', { name: 'Chronologie du mois', exact: true })).toBeVisible();
  const collectionRecord = await (await page.request.get(collectionUrl)).json();
  const timelineView = collectionRecord.views.find((item: { name: string }) => item.name === 'Chronologie équipe');

  const timeline = main.getByRole('region', { name: 'Chronologie du mois', exact: true });
  await expect(timeline.getByRole('heading', { name: 'novembre 2026', exact: true })).toBeVisible();
  const rangeRow = timeline.locator('.docs-timeline-row').filter({ hasText: 'Traversée' });
  const rangeStyle = await rangeRow.locator('.docs-timeline-bar').getAttribute('style');
  expect(rangeStyle).toContain('--first: 1');
  expect(rangeStyle).toContain('--length: 7');
  const track = rangeRow.locator('.docs-timeline-track');
  const [trackBox, rangeBox] = await Promise.all([track.boundingBox(), rangeRow.locator('.docs-timeline-bar').boundingBox()]);
  expect(trackBox).not.toBeNull(); expect(rangeBox).not.toBeNull();
  const dayWidth = trackBox!.width / 30;
  expect(Math.abs(rangeBox!.x - trackBox!.x)).toBeLessThan(dayWidth);
  expect(rangeBox!.width).toBeGreaterThan(dayWidth * 6.6);
  expect(rangeBox!.width).toBeLessThan(dayWidth * 7.4);
  const firstMilestone = timeline.locator('.docs-timeline-row').filter({ hasText: 'Jalon début' });
  const finalMilestone = timeline.locator('.docs-timeline-row').filter({ hasText: 'Jalon fin' });
  await expect(firstMilestone.locator('.docs-timeline-milestone')).toHaveCount(1);
  await expect(finalMilestone.locator('.docs-timeline-milestone')).toHaveCount(1);
  const sameDayRow = timeline.locator('.docs-timeline-row').filter({ hasText: 'Même jour' });
  expect(await sameDayRow.locator('.docs-timeline-bar').getAttribute('style')).toContain('--length: 1');
  const trailingRow = timeline.locator('.docs-timeline-row').filter({ hasText: 'Fin après mois' });
  const trailingBar = trailingRow.locator('.docs-timeline-bar');
  await expect(trailingBar.locator('.docs-timeline-overflow-start')).toHaveCount(0);
  const [trailingBox, trailingArrowBox] = await Promise.all([
    trailingBar.boundingBox(), trailingBar.locator('.docs-timeline-overflow-end').boundingBox(),
  ]);
  expect(trailingBox).not.toBeNull(); expect(trailingArrowBox).not.toBeNull();
  expect(trailingArrowBox!.x).toBeGreaterThan(trailingBox!.x + trailingBox!.width / 2);
  expect(trailingBox!.x + trailingBox!.width - (trailingArrowBox!.x + trailingArrowBox!.width)).toBeLessThan(dayWidth);
  await expect(timeline.getByRole('region', { name: 'Sans date', exact: true }).getByRole('link', { name: 'Sans dates', exact: true })).toBeVisible();
  await expect(timeline.getByRole('region', { name: 'Dates à corriger', exact: true }).getByRole('link', { name: 'Dates inversées', exact: true })).toBeVisible();
  await expect(timeline.getByRole('link', { name: 'Exclue', exact: true })).toHaveCount(0);
  await expect(timeline.getByRole('link', { name: 'Corbeille', exact: true })).toHaveCount(0);
  expect((await page.request.post(base + '/trash/' + trashOperation.id + '/restore', { data: {} })).ok()).toBeTruthy();
  const timelineAddress = new URL(page.url());
  timelineAddress.searchParams.set('docView', timelineView.id);
  await page.goto(timelineAddress.href);
  await expect(timeline.locator('.docs-timeline-row').getByRole('link')).toHaveText([
    'Corbeille', 'Fin après mois', 'Jalon début', 'Jalon fin', 'Même jour', 'Traversée',
  ]);
  await timeline.getByRole('button', { name: 'Mois précédent', exact: true }).click();
  await timeline.getByRole('button', { name: 'Mois précédent', exact: true }).click();
  await expect(timeline.getByText('Aucune page planifiée ce mois-ci.', { exact: true })).toBeVisible();
  await expect(timeline.getByText('Aucune page ne correspond aux filtres.', { exact: true })).toHaveCount(0);
  await timeline.getByRole('button', { name: 'Mois suivant', exact: true }).click();
  const octoberRange = timeline.locator('.docs-timeline-row').filter({ hasText: 'Traversée' });
  expect(await octoberRange.locator('.docs-timeline-bar').getAttribute('style')).toContain('--length: 4');
  await timeline.getByRole('button', { name: 'Mois suivant', exact: true }).click();
  await timeline.getByRole('button', { name: 'Mois suivant', exact: true }).click();
  await expect(timeline.getByRole('heading', { name: 'décembre 2026', exact: true })).toBeVisible();
  const decemberRange = timeline.locator('.docs-timeline-row').filter({ hasText: 'Année traversée' });
  expect(await decemberRange.locator('.docs-timeline-bar').getAttribute('style')).toContain('--length: 3');
  await timeline.getByRole('button', { name: 'Mois suivant', exact: true }).click();
  await expect(timeline.getByRole('heading', { name: 'janvier 2027', exact: true })).toBeVisible();
  const januaryRange = timeline.locator('.docs-timeline-row').filter({ hasText: 'Année traversée' });
  expect(await januaryRange.locator('.docs-timeline-bar').getAttribute('style')).toContain('--length: 3');

  const host = await create(page, base + '/pages', { title: 'Résumé Chronologie' });
  expect((await page.request.patch(base + '/pages/' + host.id + '/body', { data: {
    markdown: '[Chronologie équipe](/collections/' + collection.id + '/views/' + timelineView.id + ')\n\n[Chronologie équipe](/collections/' + collection.id + '/views/' + timelineView.id + ')', revision: 1,
  } })).ok()).toBeTruthy();
  const hostAddress = new URL(page.url());
  hostAddress.searchParams.set('docs', host.id);
  await page.goto(hostAddress.href);
  const embeddedViews = main.getByRole('region', { name: 'Chronologie équipe', exact: true });
  await expect(embeddedViews).toHaveCount(2);
  const embedded = embeddedViews.first()
    .getByRole('region', { name: 'Chronologie du mois', exact: true });
  await expect(embedded.getByRole('heading', { name: 'novembre 2026', exact: true })).toBeVisible();
  await embedded.evaluate(node => { (node as HTMLElement).style.width = '500px'; });
  await expect(embedded.locator('.docs-timeline-axis')).toBeHidden();
  await expect(embedded.locator('.docs-timeline-mobile-row').filter({ hasText: 'Fin après mois' })).toBeVisible();
  await embedded.evaluate(node => { (node as HTMLElement).style.width = ''; });
  await embedded.getByRole('button', { name: 'Mois précédent', exact: true }).click();
  await expect(embedded.getByRole('heading', { name: 'octobre 2026', exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(embedded.locator('.docs-timeline-mobile-row').getByRole('link')).toHaveText(['Traversée']);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);

  const collectionAddress = new URL(page.url());
  collectionAddress.searchParams.set('docs', collection.id);
  collectionAddress.searchParams.set('docView', timelineView.id);
  await page.goto(collectionAddress.href);
  await mainButton('Vue').click();
  await dialog.getByRole('textbox', { name: 'Nom de la vue', exact: true }).fill('Chronologie par défaut');
  await dialog.getByRole('combobox', { name: 'Présentation', exact: true }).selectOption('timeline');
  const defaultStart = dialog.getByRole('combobox', { name: 'Propriété de début', exact: true });
  const defaultEnd = dialog.getByRole('combobox', { name: 'Propriété de fin', exact: true });
  await expect(defaultStart).toHaveValue(start.id);
  await expect(defaultEnd).toHaveValue(end.id);
  await defaultStart.selectOption(end.id);
  await expect(defaultEnd).toHaveValue(start.id);
  await dialog.getByRole('button', { name: 'Ajouter un filtre', exact: true }).click();
  await dialog.getByRole('combobox', { name: 'Propriété du filtre', exact: true }).selectOption(state.id);
  await dialog.getByRole('combobox', { name: 'Est égal à', exact: true }).selectOption('Terminé');
  await dialog.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(main.getByText('Aucune page ne correspond aux filtres.', { exact: true })).toBeVisible();
  const defaultView = (await (await page.request.get(collectionUrl)).json()).views.find((item: { name: string }) => item.name === 'Chronologie par défaut');
  expect(defaultView.dateFieldId).toBe(end.id);
  expect(defaultView.endDateFieldId).toBe(start.id);
  await mainButton('Chronologie équipe').click();
  await page.setViewportSize({ width: 390, height: 844 });
  const keyboardLink = main.locator('.docs-timeline-mobile-row').getByRole('link', { name: 'Traversée', exact: true });
  await keyboardLink.focus(); await keyboardLink.press('Enter');
  await expect(main.getByRole('heading', { level: 1, name: 'Traversée', exact: true })).toBeVisible();
});
