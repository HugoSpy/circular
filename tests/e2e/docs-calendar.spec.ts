import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';

test.use({ timezoneId: 'America/Los_Angeles' });

async function create(page: Page, url: string, data: object) {
  const response = await page.request.post(url, { data });
  expect(response.status()).toBe(201);
  return response.json();
}

test('la vue calendrier partage les filtres, les résultats et les pages intégrées', async ({ page, app }) => {
  await page.clock.install({ time: new Date('2026-11-24T18:00:00Z') });
  await app.page.getByRole('button', { name: 'Docs', exact: true }).click();
  const main = page.getByRole('main');
  const exported = await main.getByRole('link', { name: 'Exporter', exact: true }).getAttribute('href');
  const base = new URL(exported!, page.url()).href.replace(/\/export$/, '');
  const collection = await create(page, base + '/collections', { title: 'Échéances' });
  const collectionUrl = base + '/collections/' + collection.id;
  const date = await create(page, collectionUrl + '/fields', { name: 'Date prévue', kind: 'date' });
  const status = await create(page, collectionUrl + '/fields', { name: 'État', kind: 'select', options: ['En cours', 'À faire'] });
  const hours = await create(page, collectionUrl + '/fields', { name: 'Heures', kind: 'number' });
  const doubled = await create(page, collectionUrl + '/fields', {
    name: 'Charge calculée', kind: 'formula', formula: { expression: '{' + hours.id + '} * 2' },
  });
  const entries = [];
  for (const title of ['Zèbre', 'Alpha', 'Exclue', 'Autre jour', 'Sans date', 'Corbeille']) {
    entries.push(await create(page, base + '/pages', { title, collectionId: collection.id }));
  }
  const [zebra, alpha, excluded, otherDay, undated, trashed] = entries;
  const idFirst = zebra.id.localeCompare(alpha.id) < 0 ? zebra : alpha;
  const idLast = idFirst === zebra ? alpha : zebra;
  expect((await page.request.patch(base + '/pages/' + idFirst.id + '/placement', { data: { title: 'Zèbre', parentId: null, collectionId: collection.id } })).ok()).toBeTruthy();
  expect((await page.request.patch(base + '/pages/' + idLast.id + '/placement', { data: { title: 'Alpha', parentId: null, collectionId: collection.id } })).ok()).toBeTruthy();
  const zebraTitle = idFirst === zebra ? 'Zèbre' : 'Alpha';
  const alphaTitle = idFirst === alpha ? 'Zèbre' : 'Alpha';
  const firstDay = '2026-11-04';
  const secondDay = '2026-11-12';
  const set = async (entry: { id: string }, field: { id: string }, value: unknown) => {
    expect((await page.request.patch(base + '/pages/' + entry.id + '/properties/' + field.id, { data: { value } })).ok()).toBeTruthy();
  };
  for (const entry of [zebra, alpha, excluded, trashed]) await set(entry, date, firstDay);
  await set(otherDay, date, secondDay);
  for (const entry of [zebra, alpha, otherDay, undated, trashed]) await set(entry, status, 'En cours');
  for (const [entry, value] of [[zebra, 3], [alpha, 5], [excluded, 7], [otherDay, 2], [trashed, 4]] as const) await set(entry, hours, value);
  const trash = await page.request.post(base + '/pages/' + trashed.id + '/trash', { data: { revision: trashed.revision } });
  expect(trash.status()).toBe(201);
  const trashOperation = await trash.json();

  const address = new URL(page.url());
  address.searchParams.set('docs', collection.id);
  await page.goto(address.href);
  const button = (name: string) => main.getByRole('button', { name, exact: true });
  const dialog = page.getByRole('dialog');
  await button('Vue').click();
  await dialog.getByRole('textbox', { name: 'Nom de la vue', exact: true }).fill('Calendrier équipe');
  await dialog.getByRole('combobox', { name: 'Présentation', exact: true }).selectOption('calendar');
  await dialog.getByRole('combobox', { name: 'Propriété Date', exact: true }).selectOption(date.id);
  await dialog.getByRole('button', { name: 'Ajouter un filtre', exact: true }).click();
  await dialog.getByRole('combobox', { name: 'Propriété du filtre', exact: true }).selectOption(status.id);
  await dialog.getByRole('combobox', { name: 'Est égal à', exact: true }).selectOption('En cours');
  await dialog.getByRole('button', { name: 'Ajouter un tri', exact: true }).click();
  await dialog.getByRole('combobox', { name: 'Propriété du tri 1', exact: true }).selectOption(hours.id);
  await dialog.getByRole('combobox', { name: 'Ordre du tri 1', exact: true }).selectOption('asc');
  await dialog.getByRole('button', { name: 'Enregistrer', exact: true }).click();

  const calendar = main.getByRole('region', { name: 'Calendrier du mois', exact: true });
  const dayName = new Intl.DateTimeFormat('fr-FR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' })
    .format(new Date(firstDay + 'T00:00:00Z'));
  const cell = calendar.getByRole('cell', { name: dayName, exact: true });
  await expect(cell.getByRole('link')).toHaveText([zebraTitle, alphaTitle]);
  await expect(cell.getByRole('link', { name: 'Exclue', exact: true })).toHaveCount(0);
  const alphaEvent = cell.locator('article').nth(1);
  await expect(alphaEvent.getByRole('link', { name: alphaTitle, exact: true })).toBeVisible();
  await expect(alphaEvent.getByText('4 nov.', { exact: true })).toBeVisible();
  await expect(alphaEvent.getByText('Charge calculée', { exact: true })).toBeVisible();
  await expect(alphaEvent.getByText('10', { exact: true })).toBeVisible();
  await expect(main.getByRole('spinbutton', { name: 'Charge calculée — ' + alphaTitle, exact: true })).toHaveCount(0);
  await expect(main.getByRole('region', { name: 'Sans date', exact: true }).getByRole('link', { name: 'Sans date', exact: true })).toBeVisible();
  await expect(calendar.getByRole('link', { name: 'Corbeille', exact: true })).toHaveCount(0);
  const savedCollection = await (await page.request.get(collectionUrl)).json();
  const savedView = savedCollection.views.find((view: { name: string }) => view.name === 'Calendrier équipe');

  const fallbackView = await create(page, collectionUrl + '/views', {
    name: 'Calendrier par date', layout: 'calendar', groupBy: null, dateFieldId: date.id,
    filterTree: { mode: 'all', conditions: [{ fieldId: status.id, operator: 'eq', value: 'En cours' }] },
    sorts: [{ fieldId: date.id, direction: 'asc' }], hidden: [],
  });
  const fallbackAddress = new URL(page.url());
  fallbackAddress.searchParams.set('docs', collection.id);
  fallbackAddress.searchParams.set('docView', fallbackView.id);
  await page.goto(fallbackAddress.href);
  const fallbackCalendar = main.getByRole('region', { name: 'Calendrier du mois', exact: true });
  const fallbackCell = fallbackCalendar.getByRole('cell', { name: dayName, exact: true });
  await expect(fallbackCell.getByRole('link')).toHaveText(['Alpha', 'Zèbre']);
  fallbackAddress.searchParams.set('docView', savedView.id);
  await page.goto(fallbackAddress.href);

  const heading = calendar.getByRole('heading', { level: 2 });
  const monthTitle = await heading.textContent();
  await calendar.getByRole('button', { name: 'Mois précédent', exact: true }).click();
  await expect(heading).not.toHaveText(monthTitle!);
  await expect(calendar.getByText('Aucune échéance ce mois-ci.', { exact: true }).first()).toBeVisible();
  await calendar.getByRole('button', { name: 'Aujourd’hui', exact: true }).focus();
  await calendar.getByRole('button', { name: 'Aujourd’hui', exact: true }).press('Enter');
  await expect(heading).toHaveText(monthTitle!);
  await calendar.getByRole('button', { name: 'Mois suivant', exact: true }).click();
  await expect(heading).not.toHaveText(monthTitle!);
  await calendar.getByRole('button', { name: 'Mois précédent', exact: true }).click();
  await expect(heading).toHaveText(monthTitle!);

  const host = await create(page, base + '/pages', { title: 'Résumé du calendrier' });
  expect((await page.request.patch(base + '/pages/' + host.id + '/body', {
    data: { markdown: '[Calendrier équipe](/collections/' + collection.id + '/views/' + savedView.id + ')\n\n[Calendrier équipe](/collections/' + collection.id + '/views/' + savedView.id + ')', revision: 1 },
  })).ok()).toBeTruthy();
  const hostAddress = new URL(page.url());
  hostAddress.searchParams.set('docs', host.id);
  await page.goto(hostAddress.href);
  const embeddedViews = main.getByRole('region', { name: 'Calendrier équipe', exact: true });
  await expect(embeddedViews).toHaveCount(2);
  const undatedRegions = await main.locator('section.docs-calendar-undated').evaluateAll(nodes => nodes.map(node => {
    const id = node.getAttribute('aria-labelledby');
    const title = id ? document.getElementById(id) : null;
    return { id, titleText: title?.textContent?.trim() ?? null, titleInRegion: title?.closest('section.docs-calendar-undated') === node };
  }));
  expect(undatedRegions).toHaveLength(2);
  expect(undatedRegions.every(item => item.id && item.titleText === 'Sans date' && item.titleInRegion)).toBeTruthy();
  expect(new Set(undatedRegions.map(item => item.id)).size).toBe(2);
  const embedded = embeddedViews.first();
  const embeddedCalendar = embedded.getByRole('region', { name: 'Calendrier du mois', exact: true });
  const embeddedCell = embeddedCalendar.getByRole('cell', { name: dayName, exact: true });
  await expect(embeddedCell.getByRole('link')).toHaveText([zebraTitle, alphaTitle]);
  await expect(embedded.getByRole('region', { name: 'Sans date', exact: true }).getByRole('link', { name: 'Sans date', exact: true })).toBeVisible();

  const restored = await page.request.post(base + '/trash/' + trashOperation.id + '/restore', { data: {} });
  expect(restored.ok()).toBeTruthy();
  await page.reload();
  const restoredCalendar = main.getByRole('region', { name: 'Calendrier équipe', exact: true }).first()
    .getByRole('region', { name: 'Calendrier du mois', exact: true });
  await expect(restoredCalendar.getByRole('cell', { name: dayName, exact: true }).getByRole('link'))
    .toHaveText([zebraTitle, 'Corbeille', alphaTitle]);

  await page.setViewportSize({ width: 390, height: 844 });
  const agenda = main.getByRole('region', { name: 'Calendrier équipe', exact: true }).first()
    .getByRole('region', { name: 'Agenda du mois', exact: true });
  await expect(agenda.getByRole('link')).toHaveText([zebraTitle, 'Corbeille', alphaTitle, 'Autre jour']);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  await page.setViewportSize({ width: 768, height: 900 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(768);
  const narrowCalendar = main.getByRole('region', { name: 'Calendrier équipe', exact: true }).first();
  const propertyWidths = await narrowCalendar.locator('.docs-calendar-properties dd').evaluateAll(nodes =>
    nodes.map(node => node.scrollWidth <= node.clientWidth));
  expect(propertyWidths.length).toBeGreaterThan(0);
  expect(propertyWidths.every(Boolean)).toBeTruthy();
  const narrowMonth = narrowCalendar.getByRole('region', { name: 'Calendrier du mois', exact: true });
  const todayCell = narrowMonth.getByRole('cell', { name: 'mardi 24 novembre 2026', exact: true });
  const todayBadge = todayCell.getByText('Aujourd’hui', { exact: true });
  const [cellRect, badgeRect] = await Promise.all([todayCell.boundingBox(), todayBadge.boundingBox()]);
  expect(cellRect).not.toBeNull();
  expect(badgeRect).not.toBeNull();
  expect(badgeRect!.x).toBeGreaterThanOrEqual(cellRect!.x);
  expect(badgeRect!.x + badgeRect!.width).toBeLessThanOrEqual(cellRect!.x + cellRect!.width);
});
