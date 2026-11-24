import type { APIRequestContext } from '@playwright/test';
import { expect, test } from './fixtures';

async function create(request: APIRequestContext, endpoint: string, data: object) {
  const response = await request.post(endpoint, { data });
  expect(response.status()).toBe(201);
  return response.json();
}

test('les vues partagent les propriétés et gardent les filtres composés après rechargement', async ({ app, page }) => {
  const current = new URL(app.page.url());
  const spaces = await (await page.request.get(current.origin + '/api/workspaces')).json() as { id: number; slug: string }[];
  const workspace = spaces.find(item => item.slug === current.searchParams.get('workspace'));
  if (!workspace) throw new Error('Espace de test introuvable.');
  const docs = current.origin + '/api/workspaces/' + workspace.id + '/docs';
  const collection = await create(page.request, docs + '/collections', { title: 'Bibliothèque' });
  const path = docs + '/collections/' + collection.id;
  const stage = await create(page.request, path + '/fields', { name: 'État', kind: 'select', options: ['Idée', 'À relire', 'Publié'] });
  const date = await create(page.request, path + '/fields', { name: 'Dernière revue', kind: 'date' });
  const topics = await create(page.request, path + '/fields', { name: 'Thèmes', kind: 'multi', options: ['Équipe', 'Atelier'] });
  const source = await create(page.request, path + '/fields', { name: 'Documentation', kind: 'url' });
  const rows = await Promise.all(['Kit d’atelier', 'Guide du studio', 'Repères'].map(title =>
    create(page.request, docs + '/pages', { title, collectionId: collection.id })));
  const [kit, guide, reference] = rows;
  const properties = (id: string) => docs + '/pages/' + id + '/properties/';
  async function set(pageId: string, fieldId: string, value: unknown) {
    expect((await page.request.patch(properties(pageId) + fieldId, { data: { value } })).ok()).toBeTruthy();
  }
  await set(kit.id, stage.id, 'À relire');
  await set(guide.id, stage.id, 'Publié');
  await set(reference.id, stage.id, 'Idée');
  for (const row of rows) await set(row.id, date.id, '2026-11-23');
  current.searchParams.set('docs', collection.id);
  await page.goto(current.href);

  const main = page.getByRole('main');
  const dialog = () => page.getByRole('dialog');
  const button = (name: string) => main.getByRole('button', { name, exact: true });
  const lane = (name: string) => main.getByRole('region', { name, exact: true });
  const save = () => dialog().getByRole('button', { name: 'Enregistrer', exact: true }).click();
  const card = (column: string) => lane(column).getByRole('link', { name: 'Kit d’atelier', exact: true });
  await button('Vue').click();
  await dialog().getByLabel('Nom de la vue', { exact: true }).fill('Kanban');
  await dialog().getByRole('combobox', { name: 'Présentation', exact: true }).selectOption('board');
  await dialog().getByRole('combobox', { name: 'Regrouper par', exact: true }).selectOption(stage.id);
  await save();
  await expect(card('À relire')).toBeVisible();

  const moveEndpoint = properties(kit.id) + stage.id;
  await page.route(moveEndpoint, route => route.fulfill({ status: 422, json: { error: 'Option indisponible.' } }), { times: 1 });
  await card('À relire').locator('..').dragTo(lane('Publié'));
  await expect(main.getByRole('alert')).toContainText('Option indisponible.');
  await expect(card('À relire')).toBeVisible();
  await card('À relire').locator('..').dragTo(lane('Publié'));
  await expect(card('Publié')).toBeVisible();

  await button('Vue').click();
  await dialog().getByLabel('Nom de la vue', { exact: true }).fill('Liste préparée');
  await dialog().getByRole('combobox', { name: 'Présentation', exact: true }).selectOption('list');
  await dialog().getByRole('button', { name: 'Ajouter un filtre', exact: true }).click();
  await dialog().getByRole('combobox', { name: 'Propriété du filtre' }).first().selectOption(date.id);
  await dialog().getByRole('combobox', { name: 'Opérateur' }).first().selectOption('gte');
  await dialog().getByLabel('Valeur', { exact: true }).fill('2026-11-22');
  await dialog().getByRole('button', { name: 'Ajouter un groupe', exact: true }).click();
  await dialog().getByRole('combobox', { name: 'Est égal à', exact: true }).nth(0).selectOption('Publié');
  await dialog().getByRole('combobox', { name: 'Est égal à', exact: true }).nth(1).selectOption('À relire');
  await dialog().getByRole('button', { name: 'Ajouter un tri', exact: true }).click();
  await dialog().getByRole('button', { name: 'Ajouter un tri', exact: true }).click();
  await dialog().getByRole('button', { name: 'Remonter le tri 2', exact: true }).click();
  await save();
  const list = main.getByRole('list');
  await expect(list.getByRole('link')).toHaveText(['Guide du studio', 'Kit d’atelier']);

  await button('Propriétés').click();
  await dialog().getByRole('button', { name: 'Modifier État', exact: true }).click();
  await dialog().getByRole('textbox', { name: 'Nom', exact: true }).fill('Publication');
  await dialog().getByRole('textbox', { name: 'Option 3', exact: true }).fill('Prêt');
  await save();
  await dialog().getByRole('button', { name: 'Fermer', exact: true }).last().click();
  await expect(list.getByRole('listitem').first()).toContainText('Prêt');
  await expect(list.getByRole('link')).toHaveCount(2);

  const canonical = page.url();
  await page.setViewportSize({ width: 390, height: 844 });
  await button('Kanban').click();
  await expect(card('Prêt')).toBeVisible();
  await lane('Prêt').getByRole('button', { name: 'Déplacer Kit d’atelier', exact: true }).click();
  await dialog().getByRole('combobox', { name: 'Nouvelle colonne', exact: true }).selectOption('Idée');
  await dialog().getByRole('button', { name: 'Déplacer', exact: true }).click();
  await expect(card('Idée')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);

  const apiPage = docs + '/pages/' + kit.id;
  expect((await (await page.request.get(apiPage)).json()).properties[stage.id]).toBe('Idée');
  await card('Idée').click();
  await expect(main.getByRole('heading', { name: 'Kit d’atelier', exact: true })).toBeVisible();
  await expect(main.getByRole('combobox', { name: 'Publication', exact: true })).toHaveValue('Idée');
  await button('Modifier Thèmes').click();
  await dialog().getByRole('checkbox', { name: 'Équipe', exact: true }).check();
  await save();
  await button('Modifier Documentation').click();
  await dialog().getByLabel('Adresse URL', { exact: true }).fill('https://example.org/atelier');
  await save();
  await expect(main.getByRole('link', { name: 'https://example.org/atelier', exact: true })).toBeVisible();
  expect((await (await page.request.get(apiPage)).json()).properties).toMatchObject({
    [stage.id]: 'Idée', [topics.id]: ['Équipe'], [source.id]: 'https://example.org/atelier',
  });

  await page.goto(canonical);
  const table = main.getByRole('table');
  const row = table.getByRole('row', { name: /Kit d’atelier/ });
  await expect(row.getByRole('combobox', { name: 'Publication — Kit d’atelier', exact: true })).toHaveValue('Idée');
  await expect(row).toContainText('Équipe');
  await button('Liste préparée').click();
  await expect(list.getByRole('link')).toHaveText(['Guide du studio']);
});
