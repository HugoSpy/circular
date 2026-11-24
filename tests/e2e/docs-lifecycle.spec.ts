import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';

async function docsPageEndpoint(page: Page) {
  const address = new URL(page.url());
  const workspaces = await page.request.get(address.origin + '/api/workspaces');
  expect(workspaces.ok()).toBeTruthy();
  const spaces: { id: number; slug: string }[] = await workspaces.json();
  const current = spaces.find(space => space.slug === address.searchParams.get('workspace'));
  if (!current) throw new Error('Espace du scénario introuvable.');
  return address.origin + `/api/workspaces/${current.id}/docs/pages/${address.searchParams.get('docs')}`;
}

test('l’historique protège des conflits et la corbeille restaure le sous-arbre', async ({ app, page }) => {
  const main = app.page.getByRole('main');
  const nav = page.getByRole('navigation', { name: 'Pages de l’espace' }).or(page.getByRole('region', { name: 'Pages de l’espace' }));
  const heading = (name: string) => main.getByRole('heading', { name, exact: true });
  const dialog = () => page.getByRole('dialog');
  const editor = main.getByRole('textbox', { name: 'Contenu de la page', exact: true });
  const saveStatus = main.locator('.docs-editor').getByRole('status');

  async function create(title: string) {
    await dialog().getByRole('textbox', { name: 'Titre', exact: true }).fill(title);
    await dialog().getByRole('button', { name: 'Créer la page', exact: true }).click();
    await expect(heading(title)).toBeVisible();
  }
  await page.getByRole('button', { name: 'Docs', exact: true }).click();
  await main.getByRole('button', { name: 'Nouvelle page', exact: true }).click();
  await create('Guide initial');
  const rootUrl = page.url();
  const endpoint = await docsPageEndpoint(page);
  await editor.fill('Version à retrouver');
  await expect(saveStatus).toHaveText('Enregistré');
  await editor.fill('Version récente');
  await expect(saveStatus).toHaveText('Enregistré');

  await main.getByRole('button', { name: 'Paramètres de la page', exact: true }).click();
  await dialog().getByRole('textbox', { name: 'Titre', exact: true }).fill('Guide renommé');
  await dialog().getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await expect(heading('Guide renommé')).toBeVisible();
  await main.getByRole('button', { name: 'Sous-page', exact: true }).click();
  await create('Sous-page à restaurer');
  const childUrl = page.url();
  await nav.getByRole('link', { name: 'Guide renommé', exact: true }).click();
  await expect(heading('Guide renommé')).toBeVisible();

  await page.route(endpoint + '/body', route => route.fulfill({ status: 503, json: { error: 'Sauvegarde temporairement indisponible.' } }));
  await editor.fill('Brouillon à préserver');
  await expect(saveStatus).toHaveText('Brouillon non enregistré');
  await main.getByRole('button', { name: 'Historique', exact: true }).click();
  await dialog().getByRole('button', { name: /^Révision 2/ }).click();
  await expect(dialog().getByText('Version à retrouver', { exact: true })).toBeVisible();
  await expect(dialog().getByText('Version récente', { exact: true })).toBeVisible();
  const current = await page.request.get(endpoint);
  const data = await current.json();
  const update = await page.request.patch(endpoint + '/body', { data: { markdown: 'Édition concurrente', revision: data.revision } });
  expect(update.ok()).toBeTruthy();
  await dialog().getByRole('button', { name: 'Restaurer la révision 2', exact: true }).click();
  await expect(dialog().getByRole('button', { name: 'Annuler', exact: true })).toBeFocused();
  page.once('dialog', confirmation => confirmation.accept());
  await dialog().getByRole('button', { name: 'Restaurer la révision', exact: true }).click();
  await expect(dialog().getByRole('alert')).toContainText('La page a changé');
  await expect(main.locator('.docs-editor [contenteditable=true]')).toHaveText('Brouillon à préserver');
  await dialog().getByRole('button', { name: 'Actualiser la comparaison', exact: true }).click();
  await expect(dialog().getByText('Édition concurrente', { exact: true })).toBeVisible();
  await dialog().getByRole('button', { name: 'Restaurer la révision 2', exact: true }).click();
  page.once('dialog', confirmation => confirmation.accept());
  await dialog().getByRole('button', { name: 'Restaurer la révision', exact: true }).click();
  await expect(heading('Guide initial')).toBeVisible();
  await page.unroute(endpoint + '/body');
  await expect(editor).toHaveText('Version à retrouver');
  await expect(main.getByText('Révision 6 créée.', { exact: true })).toBeVisible();
  expect(page.url()).toBe(rootUrl);

  await main.getByText('Actions de la page', { exact: true }).click();
  await main.getByRole('button', { name: 'Dupliquer la page', exact: true }).click();
  await expect(heading('Copie de Guide initial')).toBeVisible();
  await expect(editor).toHaveText('Version à retrouver');
  expect(page.url()).not.toBe(rootUrl);
  await nav.getByRole('link', { name: 'Guide initial', exact: true }).click();
  await expect(heading('Guide initial')).toBeVisible();
  await main.getByText('Actions de la page', { exact: true }).click();
  await main.getByRole('button', { name: 'Mettre à la corbeille', exact: true }).click();
  await expect(dialog().getByText(/1 sous-page/)).toBeVisible();
  await dialog().getByRole('button', { name: 'Mettre à la corbeille', exact: true }).click();
  await expect(heading('Corbeille')).toBeVisible();
  await expect(main.getByText('2 pages mises à la corbeille.', { exact: true })).toBeVisible();
  await expect(nav.getByRole('link', { name: 'Sous-page à restaurer', exact: true })).toHaveCount(0);
  expect((await page.request.get(endpoint)).status()).toBe(404);
  await page.setViewportSize({ width: 390, height: 844 });
  await main.getByRole('button', { name: 'Restaurer Guide initial', exact: true }).click();
  await dialog().getByRole('button', { name: 'Restaurer', exact: true }).click();
  await expect(heading('Guide initial')).toBeVisible();
  expect(page.url()).toBe(rootUrl);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  await main.getByRole('button', { name: 'Ouvrir la navigation Docs' }).click();
  await nav.getByRole('link', { name: 'Sous-page à restaurer', exact: true }).click();
  await expect(heading('Sous-page à restaurer')).toBeVisible();
  expect(page.url()).toBe(childUrl);
  await main.getByRole('button', { name: 'Ouvrir la navigation Docs' }).click();
  await page.getByRole('link', { name: 'Corbeille', exact: true }).click();
  await expect(main.getByText('La corbeille est vide.', { exact: true })).toBeVisible();
});
