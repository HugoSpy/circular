import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';

async function create(page: Page, url: string, data: object) {
  const response = await page.request.post(url, { data });
  expect(response.status()).toBe(201);
  return response.json();
}

test.use({ hasTouch: true });

test('une agrégation alimente la fiche, la vue filtrée et le bloc intégré', async ({ page, app }) => {
  await app.page.getByRole('button', { name: 'Docs', exact: true }).click();
  const main = page.getByRole('main');
  const dialog = page.getByRole('dialog');
  const button = (name: string) => main.getByRole('button', { name, exact: true });
  const dialogButton = (name: string) => dialog.getByRole('button', { name, exact: true });
  const option = (name: string) => dialog.getByRole('combobox', { name, exact: true });
  const heading = (name: string) => main.getByRole('heading', { name, exact: true, level: 1 });
  const exported = await main.getByRole('link', { name: 'Exporter', exact: true }).getAttribute('href');
  const base = new URL(exported!, page.url()).href.replace(/\/export$/, '');
  const home = page.url();
  function href(id: string, view?: string) {
    const url = new URL(home);
    url.searchParams.set('docs', id);
    if (view) url.searchParams.set('docView', view);
    return url.href;
  }
  const projects = await create(page, base + '/collections', { title: 'Projets' });
  const resources = await create(page, base + '/collections', { title: 'Ressources' });
  const projectApi = base + '/collections/' + projects.id;
  const resourceApi = base + '/collections/' + resources.id;
  await page.goto(href(projects.id));
  await expect(heading('Projets')).toBeVisible();
  await expect(main.getByText('Cette collection est vide.', { exact: true })).toBeVisible();
  const hours = await create(page, resourceApi + '/fields', { name: 'Heures', kind: 'number' });
  const phase = await create(page, projectApi + '/fields', { name: 'État', kind: 'select', options: ['À faire'] });
  const relation = await create(page, projectApi + '/fields', { name: 'Ressources liées', kind: 'relation', targetCollectionId: resources.id });
  const rows = [];
  for (const title of ['Atelier', 'Bilan', 'Contrôle', 'Simulation']) {
    rows.push(await create(page, base + '/pages', { title, collectionId: projects.id }));
  }
  const targets = [];
  for (const [title, value] of [['Repérage', 6], ['Ajustement', -2], ['Vérification', 0], ['Notes', null],
      ['Grand nombre A', Number.MAX_SAFE_INTEGER], ['Grand nombre B', Number.MAX_SAFE_INTEGER]] as const) {
    const target = await create(page, base + '/pages', { title, collectionId: resources.id });
    targets.push(target);
    if (value !== null) expect((await page.request.patch(base + '/pages/' + target.id + '/properties/' + hours.id, { data: { value } })).ok()).toBeTruthy();
  }
  for (const [project, linked] of [[rows[0], targets.slice(0, 4)], [rows[2], [targets[2]]], [rows[3], targets.slice(4)]] as const) {
    expect((await page.request.patch(base + '/pages/' + project.id + '/relations/' + relation.id, {
      data: { add: linked.map(item => item.id) },
    })).ok()).toBeTruthy();
  }
  await page.reload();
  await button('Propriétés').press('Enter');
  await dialogButton('Ajouter une propriété').press('Enter');
  await dialog.getByRole('textbox', { name: 'Nom', exact: true }).fill('Total heures');
  await option('Type').selectOption('aggregate');
  await expect(option('Calcul')).toBeDisabled();
  await option('Relation').selectOption(relation.id);
  await option('Calcul').selectOption('sum');
  await option('Propriété source').selectOption(hours.id);
  await dialogButton('Ajouter la propriété').press('Enter');
  await expect(dialog.getByText('Agrégation · Somme', { exact: true })).toBeVisible();
  await dialogButton('Fermer').last().click();

  const table = main.getByRole('table');
  const row = (title: string) => table.getByRole('row').filter({ has: page.getByRole('link', { name: title, exact: true }) });
  await expect(row('Atelier').getByRole('cell').last()).toHaveText('4');
  await expect(row('Atelier').getByRole('cell').last().getByRole('spinbutton')).toHaveCount(0);
  await expect(row('Bilan').getByRole('cell').last()).toHaveText('Sans valeur');
  await expect(row('Contrôle').getByRole('cell').last()).toHaveText('0');
  await expect(row('Simulation').getByRole('cell').last()).toHaveText('Résultat hors plage');
  const links = (pane = main) => pane.getByRole('table').locator('tbody tr td:first-child a');
  const collection = await (await page.request.get(projectApi)).json();
  const aggregate = collection.fields.find((item: { name: string }) => item.name === 'Total heures');

  await button('Configurer la vue').click();
  await option('Propriété du tri 1').selectOption(aggregate.id);
  await dialogButton('Enregistrer').click();
  await expect(links()).toHaveText(['Contrôle', 'Atelier', 'Bilan', 'Simulation']);

  await button('Configurer la vue').click();
  await dialogButton('Ajouter un groupe').click();
  await option('Propriété du filtre').nth(0).selectOption(aggregate.id);
  await option('Opérateur').nth(0).selectOption('gte');
  await dialog.getByRole('spinbutton', { name: 'Valeur', exact: true }).fill('0');
  await option('Propriété du filtre').nth(1).selectOption(aggregate.id);
  await option('Opérateur').nth(1).selectOption('empty');
  await dialogButton('Enregistrer').click();
  await expect(links()).toHaveText(['Contrôle', 'Atelier', 'Bilan']);

  await button('Configurer la vue').click();
  await dialogButton('Retirer le groupe').click();
  await dialogButton('Ajouter un filtre').click();
  await option('Propriété du filtre').selectOption(aggregate.id);
  await option('Opérateur').selectOption('filled');
  await option('Ordre du tri 1').selectOption('desc');
  await dialogButton('Enregistrer').click();
  await expect(links()).toHaveText(['Atelier', 'Contrôle']);

  const view = collection.views[0];
  const host = await create(page, base + '/pages', { title: 'Synthèse' });
  const markdown = '[Projets — Toutes les pages](/collections/' + projects.id + '/views/' + view.id + ')';
  expect((await page.request.patch(base + '/pages/' + host.id + '/body', { data: { markdown, revision: 1 } })).ok()).toBeTruthy();
  await page.goto(href(host.id));
  const embedded = main.getByRole('region', { name: 'Toutes les pages', exact: true });
  await expect(links(embedded)).toHaveText(['Atelier', 'Contrôle']);
  await expect(embedded.getByRole('cell', { name: '4', exact: true })).toBeVisible();
  await embedded.getByRole('link', { name: 'Atelier', exact: true }).click();
  await expect(heading('Atelier')).toBeVisible();
  const properties = main.getByRole('region', { name: 'Propriétés de la page' });
  await expect(properties.getByText('4', { exact: true })).toBeVisible();
  await properties.getByRole('link', { name: 'Repérage · Ressources', exact: true }).click();
  await expect(heading('Repérage')).toBeVisible();
  const input = properties.getByRole('spinbutton', { name: 'Heures', exact: true });
  await input.fill('1');
  const saved = page.waitForResponse(response => response.url().endsWith('/properties/' + hours.id) && response.request().method() === 'PATCH');
  await input.press('Enter');
  expect((await saved).ok()).toBeTruthy();
  await properties.getByRole('link', { name: 'Ressources', exact: true }).click();
  await expect(heading('Ressources')).toBeVisible();
  await page.goBack();
  await expect(heading('Repérage')).toBeVisible();
  await page.goBack();
  await expect(heading('Atelier')).toBeVisible();
  await expect(properties.getByText('-1', { exact: true })).toBeVisible();
  await page.goBack();
  await expect(links(embedded)).toHaveText(['Contrôle', 'Atelier']);

  const list = await create(page, projectApi + '/views', { name: 'Liste', layout: 'list' });
  const board = await create(page, projectApi + '/views', { name: 'Kanban', layout: 'board', groupBy: phase.id });
  for (const [layout, selector] of [[list, 'li'], [board, 'article']] as const) {
    await page.goto(href(projects.id, layout.id));
    const card = main.locator(selector).filter({ has: page.getByRole('link', { name: 'Atelier', exact: true }) }).filter({ hasText: 'Total heures' });
    await expect(card.getByText('-1', { exact: true })).toBeVisible();
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await button('Propriétés').tap();
  await dialogButton('Modifier Total heures').tap();
  await expect(dialog.getByText('Propriété source · Heures', { exact: true })).toBeVisible();
  await expect(dialog.getByText('Calcul · Somme', { exact: true })).toBeVisible();
  await expect(option('Calcul')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
});


test('les formules se configurent au clavier et refusent les cycles', async ({ page, app }) => {
  await app.page.getByRole('button', { name: 'Docs', exact: true }).click();
  const main = page.getByRole('main');
  const dialog = page.getByRole('dialog');
  const button = (name: string) => main.getByRole('button', { name, exact: true });
  const dialogButton = (name: string) => dialog.getByRole('button', { name, exact: true });
  const heading = (name: string) => main.getByRole('heading', { name, exact: true, level: 1 });
  const exported = await main.getByRole('link', { name: 'Exporter', exact: true }).getAttribute('href');
  const base = new URL(exported!, page.url()).href.replace(/\/export$/, '');
  const collection = await create(page, base + '/collections', { title: 'Calculs' });
  const collectionUrl = base + '/collections/' + collection.id;
  const number = await create(page, collectionUrl + '/fields', { name: 'Heures » facturées', kind: 'number' });
  const pageRecord = await create(page, base + '/pages', { title: 'Atelier', collectionId: collection.id });
  expect((await page.request.patch(base + '/pages/' + pageRecord.id + '/properties/' + number.id, { data: { value: 6 } })).ok()).toBeTruthy();
  const address = new URL(page.url());
  address.searchParams.set('docs', collection.id);
  await page.goto(address.href);
  await expect(heading('Calculs')).toBeVisible();
  await button('Propriétés').press('Enter');
  await dialogButton('Ajouter une propriété').press('Enter');
  await dialog.getByRole('textbox', { name: 'Nom', exact: true }).fill('Double');
  await dialog.getByRole('combobox', { name: 'Type', exact: true }).selectOption('formula');
  const formula = dialog.getByRole('textbox', { name: 'Formule', exact: true });
  await dialog.getByRole('button', { name: 'Heures » facturées', exact: true }).press('Enter');
  await formula.pressSequentially(' * 2');
  expect(await formula.inputValue()).toBe('«Heures \\» facturées» * 2');
  await dialogButton('Ajouter la propriété').press('Enter');
  await expect(dialog.getByText('Formule · Formule', { exact: true })).toBeVisible();
  await dialogButton('Fermer').last().click();
  let fields = (await (await page.request.get(collectionUrl)).json()).fields;
  const first = fields.find((field: { name: string }) => field.name === 'Double');
  await expect(main.getByRole('spinbutton', { name: 'Double — Atelier', exact: true })).toHaveCount(0);
  await expect(main.getByRole('cell', { name: '12', exact: true })).toBeVisible();
  await button('Propriétés').press('Enter');
  await dialogButton('Modifier Double').press('Enter');
  await expect(dialog.getByRole('textbox', { name: 'Formule', exact: true })).toHaveValue('«Heures \\» facturées» * 2');
  await dialogButton('Annuler').press('Enter');
  await dialogButton('Fermer').last().press('Enter');
  const second = await create(page, collectionUrl + '/fields', {
    name: 'Composé', kind: 'formula', formula: { expression: '{' + first.id + '} + 1' },
  });
  const hoursInput = main.getByRole('spinbutton', { name: 'Heures » facturées — Atelier', exact: true });
  await hoursInput.fill('8');
  const changed = page.waitForResponse(response => response.url().endsWith('/properties/' + number.id) && response.request().method() === 'PATCH');
  await hoursInput.press('Enter');
  expect((await changed).ok()).toBeTruthy();
  await expect(main.getByRole('cell', { name: '16', exact: true })).toBeVisible();
  fields = (await (await page.request.get(collectionUrl)).json()).fields;
  const cycle = await page.request.patch(collectionUrl + '/fields/' + first.id, {
    data: { name: first.name, options: [], previousOptions: [], formula: { expression: '{' + second.id + '} + 1' } },
  });
  expect(cycle.status()).toBe(422);
  const summary = (await (await page.request.get(base)).json()).pages.find((item: { id: string }) => item.id === pageRecord.id);
  expect(summary.properties[first.id]).toBe(16);
  expect(summary.properties[second.id]).toBe(17);

  const secondPage = await create(page, base + '/pages', { title: 'Deuxième', collectionId: collection.id });
  const thirdPage = await create(page, base + '/pages', { title: 'Troisième', collectionId: collection.id });
  const excludedPage = await create(page, base + '/pages', { title: 'Exclue', collectionId: collection.id });
  for (const [entry, value] of [[secondPage, 4], [thirdPage, 6], [excludedPage, 2]] as const) {
    expect((await page.request.patch(base + '/pages/' + entry.id + '/properties/' + number.id, { data: { value } })).ok()).toBeTruthy();
  }
  const view = await create(page, collectionUrl + '/views', {
    name: 'Formules triées', layout: 'table', hidden: [], sorts: [{ fieldId: first.id, direction: 'desc' }],
    filterTree: { mode: 'all', conditions: [{ fieldId: first.id, operator: 'gte', value: 8 }] },
  });
  const host = await create(page, base + '/pages', { title: 'Synthèse des formules' });
  const markdown = '[Calculs](/collections/' + collection.id + '/views/' + view.id + ')';
  expect((await page.request.patch(base + '/pages/' + host.id + '/body', { data: { markdown, revision: 1 } })).ok()).toBeTruthy();
  const hostAddress = new URL(page.url());
  hostAddress.searchParams.set('docs', host.id);
  await page.goto(hostAddress.href);
  const embedded = main.getByRole('region', { name: 'Formules triées', exact: true });
  const embeddedLinks = embedded.getByRole('table').locator('tbody tr td:first-child a');
  const embeddedRow = (title: string) => embedded.getByRole('row').filter({ has: page.getByRole('link', { name: title, exact: true }) });
  await expect(embeddedLinks).toHaveText(['Atelier', 'Troisième', 'Deuxième']);
  await expect(embeddedRow('Atelier').getByRole('cell').nth(2)).toHaveText('16');
  await expect(embeddedRow('Troisième').getByRole('cell').nth(2)).toHaveText('12');
  await expect(embeddedRow('Deuxième').getByRole('cell').nth(2)).toHaveText('8');
});
