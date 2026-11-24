import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';

async function create(page: Page, url: string, data: object) {
  const response = await page.request.post(url, { data });
  expect(response.status()).toBe(201);
  return response.json();
}

test.use({ hasTouch: true });

test('une relation créée au clavier relie les mêmes pages dans les vues et la fiche', async ({ app, page }) => {
  const main = page.getByRole('main');
  const dialog = page.getByRole('dialog');
  const button = (name: string) => main.getByRole('button', { name, exact: true });
  const heading = (name: string) => main.getByRole('heading', { name, exact: true, level: 1 });
  const save = () => dialog.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await app.page.getByRole('button', { name: 'Docs', exact: true }).click();
  const exportLink = await main.getByRole('link', { name: 'Exporter', exact: true }).getAttribute('href');
  const docs = new URL(exportLink!, page.url()).href.replace(/\/export$/, '');
  const home = page.url();

  async function collection(title: string) {
    await button('Nouvelle collection').click();
    await dialog.getByRole('textbox', { name: 'Titre', exact: true }).fill(title);
    await dialog.getByRole('button', { name: 'Créer la collection', exact: true }).click();
    await expect(heading(title)).toBeVisible();
    await expect(main.getByText('Cette collection est vide.', { exact: true })).toBeVisible();
    return page.url();
  }
  async function document(title: string) {
    await button('Nouvelle page').click();
    await dialog.getByRole('textbox', { name: 'Titre', exact: true }).fill(title);
    await dialog.getByRole('button', { name: 'Créer la page', exact: true }).click();
    await expect(heading(title)).toBeVisible();
    return page.url();
  }
  await collection('Ressources');
  const target = await document('Guide de réunion');
  await page.goto(home);
  const projects = await collection('Projets');
  const source = await document('Préparer un atelier');
  await page.goto(projects);

  await button('Propriétés').click();
  await dialog.getByRole('button', { name: 'Ajouter une propriété', exact: true }).click();
  await dialog.getByRole('textbox', { name: 'Nom', exact: true }).fill('Guides liés');
  await dialog.getByRole('combobox', { name: 'Type', exact: true }).selectOption('relation');
  await dialog.getByRole('combobox', { name: 'Collection cible', exact: true }).selectOption({ label: 'Ressources' });
  await dialog.getByRole('button', { name: 'Ajouter la propriété', exact: true }).click();
  await expect(dialog.getByText('Relation vers Ressources', { exact: true })).toBeVisible();
  await dialog.getByRole('button', { name: 'Fermer', exact: true }).last().click();

  const add = button('Ajouter Guides liés — Préparer un atelier');
  await add.press('Enter');
  const search = dialog.getByRole('searchbox', { name: 'Rechercher une page', exact: true });
  await expect(search).toBeFocused();
  await search.fill('reunion');
  const choice = dialog.getByRole('checkbox', { name: /Guide de réunion/ });
  await choice.press('Space');
  await expect(choice).toBeChecked();
  const changed = page.waitForResponse(response => response.url().includes('/relations/') && response.request().method() === 'PATCH');
  await save();
  const saved = await changed;
  expect(saved.ok()).toBeTruthy();
  const fieldId = saved.url().split('/').at(-1)!;
  const id = (url: string) => new URL(url).searchParams.get('docs');
  const sourceApi = docs + '/pages/' + id(source);
  expect((await saved.json()).properties[fieldId]).toEqual([id(target)]);
  const link = main.getByRole('link', { name: 'Guide de réunion · Ressources', exact: true });
  await expect(link).toBeVisible();
  await expect(button('Modifier Guides liés — Préparer un atelier')).toBeFocused();

  const collectionApi = docs + '/collections/' + id(projects);
  const stage = await create(page, collectionApi + '/fields', { name: 'État', kind: 'select', options: ['Prêt'] });
  await create(page, collectionApi + '/views', { name: 'Liste', layout: 'list' });
  await create(page, collectionApi + '/views', { name: 'Kanban', layout: 'board', groupBy: stage.id });
  await page.reload();
  for (const layout of ['Liste', 'Kanban', 'Toutes les pages']) {
    await button(layout).click();
    await expect(link).toBeVisible();
  }
  await main.getByRole('link', { name: 'Préparer un atelier', exact: true }).click();
  await expect(heading('Préparer un atelier')).toBeVisible();
  await expect(main.getByRole('region', { name: 'Propriétés de la page', exact: true }).getByRole('link', { name: /Guide de réunion/ })).toBeVisible();
  await link.click();
  await expect(heading('Guide de réunion')).toBeVisible();

  await main.getByText('Actions de la page', { exact: true }).click();
  await button('Mettre à la corbeille').click();
  await dialog.getByRole('button', { name: 'Mettre à la corbeille', exact: true }).click();
  await expect(heading('Corbeille')).toBeVisible();
  await page.goto(source);
  await expect(heading('Préparer un atelier')).toBeVisible();
  await expect(link).toHaveCount(0);
  expect((await (await page.request.get(sourceApi)).json()).properties).toEqual({});
  const trashed = await (await page.request.get(docs + '/trash')).json();
  const entry = trashed.find((item: { rootId: string }) => item.rootId === id(target));
  expect((await page.request.post(docs + '/trash/' + entry.id + '/restore', { data: {} })).ok()).toBeTruthy();
  await page.reload();
  await expect(link).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await button('Modifier Guides liés — Préparer un atelier').tap();
  await expect(dialog).toBeVisible();
  await choice.tap();
  await expect(choice).not.toBeChecked();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  await save();
  await expect(link).toHaveCount(0);
  expect((await (await page.request.get(sourceApi)).json()).properties).toEqual({});
});
