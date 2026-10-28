import type { Page } from '@playwright/test';
import { test, expect } from './fixtures';

const navigation = (page: Page) => page.getByRole('navigation', { name: 'Navigation principale' });
async function settings(page: Page, section?: 'Étiquettes'|'Modèles') {
  await navigation(page).getByRole('button', { name: 'Paramètres', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Votre espace de travail', exact: true })).toBeVisible();
  if (section) await page.getByRole('navigation', { name: 'Sections des paramètres' }).getByRole('button', { name: new RegExp(`^${section}`) }).click();
}
async function tickets(page: Page) { await navigation(page).getByRole('button', { name: /^Tous les tickets/ }).click(); }
async function display(page: Page) {
  await page.getByRole('button', { name: 'Affichage', exact: true }).click();
  return page.getByRole('dialog', { name: 'Options d’affichage', exact: true });
}

test('préférences sauvegardées, garde de navigation et redémarrage réel', async ({ app, page, server }, testInfo) => {
  await app.createProject('Préférences', 'PREF');
  await app.createTicket({ title: 'Préserver ma configuration' });
  await settings(page);
  await page.getByRole('combobox', { name: 'Taille du texte', exact: true }).selectOption('large');
  page.once('dialog', dialog => dialog.dismiss());
  await navigation(page).getByRole('button', { name: /^Tous les tickets/ }).click();
  await expect(page.getByRole('heading', { name: 'Paramètres', exact: true })).toBeVisible();
  await expect(page.getByRole('combobox', { name: 'Taille du texte', exact: true })).toHaveValue('large');
  await page.getByRole('combobox', { name: 'Densité', exact: true }).selectOption('comfortable');
  await page.getByRole('combobox', { name: 'Page d’accueil', exact: true }).selectOption('board');
  await page.getByRole('combobox', { name: 'Envoyer un commentaire', exact: true }).selectOption('enter');
  await page.getByRole('checkbox', { name: /Réduire les animations/ }).check();
  await page.getByRole('button', { name: 'Enregistrer les préférences', exact: true }).click();
  await expect(page.getByText('Préférences enregistrées.', { exact: true })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-font-size', 'large');
  await page.screenshot({ path: testInfo.outputPath('workspace-settings.png'), fullPage: true });
  await server.restart();
  await page.reload();
  await expect(page.getByRole('button', { name: 'Tableau', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(app.card('Préserver ma configuration')).toBeVisible();
  await settings(page);
  await expect(page.getByRole('combobox', { name: 'Taille du texte', exact: true })).toHaveValue('large');
  await expect(page.getByRole('combobox', { name: 'Densité', exact: true })).toHaveValue('comfortable');
  await expect(page.getByRole('combobox', { name: 'Envoyer un commentaire', exact: true })).toHaveValue('enter');
  await expect(page.locator('html')).toHaveAttribute('data-reduce-motion', 'true');
  const stored = await (await page.request.get(`${server.url}/api/settings`)).json();
  expect(stored).toMatchObject({ homeView: 'board', fontSize: 'large', density: 'comfortable', reduceMotion: true, commentSubmit: 'enter' });
});

test('étiquettes : création, modification et suppression répercutées sur les tickets', async ({ app, page, server }) => {
  const invalidRequests: string[] = [];
  page.on('response', response => { if ([400, 422].includes(response.status()) && response.url().includes('/api/')) invalidRequests.push(response.url()); });
  await app.createProject('Classification', 'CLAS');
  await settings(page, 'Étiquettes');
  await page.getByRole('button', { name: 'Nouvelle étiquette', exact: true }).click();
  const editor = page.getByRole('dialog');
  await editor.getByRole('textbox', { name: 'Nom de l’étiquette', exact: true }).fill('Exploration');
  await editor.getByRole('textbox', { name: 'Description de l’étiquette', exact: true }).fill('Recherche avant mise en œuvre.');
  await editor.getByRole('button', { name: 'Créer l’étiquette', exact: true }).click();
  await expect(editor).toBeHidden();
  await expect(page.getByRole('button', { name: 'Modifier l’étiquette Exploration', exact: true })).toBeVisible();
  await tickets(page);
  await page.getByRole('button', { name: 'Nouveau ticket', exact: true }).click();
  await app.fillTicket(app.newTicketDialog, { title: 'Ticket classé' });
  await app.newTicketDialog.getByRole('checkbox', { name: 'Exploration', exact: true }).check();
  await app.newTicketDialog.getByRole('button', { name: 'Créer le ticket', exact: true }).click();
  await expect(app.newTicketDialog).toBeHidden();
  await expect(app.row('Ticket classé').getByText('Exploration', { exact: true })).toBeVisible();
  await settings(page, 'Étiquettes');
  await page.getByRole('button', { name: 'Modifier l’étiquette Exploration', exact: true }).click();
  await editor.getByRole('textbox', { name: 'Nom de l’étiquette', exact: true }).fill('Recherche');
  await editor.locator('input[type=color]').fill('#ffcc22');
  await editor.getByRole('button', { name: 'Enregistrer l’étiquette', exact: true }).click();
  await expect(editor).toBeHidden();
  await tickets(page);
  await expect(app.row('Ticket classé').getByText('Recherche', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Plus de filtres', exact: true }).click();
  await page.getByRole('dialog').getByRole('checkbox', { name: 'Recherche', exact: true }).check();
  await page.getByRole('dialog').getByRole('button', { name: 'Voir les résultats', exact: true }).click();
  await expect.poll(async () => (await (await page.request.get(`${server.url}/api/settings`)).json()).filters.labelIds.length).toBe(1);
  await settings(page, 'Étiquettes');
  await page.getByRole('button', { name: 'Modifier l’étiquette Recherche', exact: true }).click();
  page.once('dialog', dialog => dialog.accept());
  await editor.getByRole('button', { name: 'Supprimer l’étiquette', exact: true }).click();
  await expect(editor).toBeHidden();
  await page.getByRole('navigation', { name: 'Sections des paramètres' }).getByRole('button', { name: 'Préférences', exact: true }).click();
  await page.getByRole('combobox', { name: 'Densité', exact: true }).selectOption('comfortable');
  await page.getByRole('button', { name: 'Enregistrer les préférences', exact: true }).click();
  await expect(page.getByText('Préférences enregistrées.', { exact: true })).toBeVisible();
  await tickets(page);
  await expect(app.row('Ticket classé').getByText('Recherche', { exact: true })).toHaveCount(0);
  await server.restart();
  await page.reload();
  expect(await (await page.request.get(`${server.url}/api/labels`)).json()).toEqual([]);
  const issues = await (await page.request.get(`${server.url}/api/issues`)).json();
  expect(issues[0].labels).toEqual([]);
  expect(invalidRequests).toEqual([]);
});

test('filtres multiples : OU dans un champ, ET entre champs, favoris et persistance', async ({ app, page, server }) => {
  await app.createProject('Filtres', 'FLT');
  const projects = await (await page.request.get(`${server.url}/api/projects`)).json();
  const labelA = await (await page.request.post(`${server.url}/api/labels`, { data: { name: 'Interface', color: '#f2cf63' } })).json();
  const labelB = await (await page.request.post(`${server.url}/api/labels`, { data: { name: 'Données', color: '#b4a1ef' } })).json();
  const drafts = [
    { title: 'Cible interface', status: 'todo', priority: 'high', labelIds: [labelA.id], isFavorite: true },
    { title: 'Cible données', status: 'in_progress', priority: 'urgent', labelIds: [labelB.id], isFavorite: false },
    { title: 'Cible terminée', status: 'done', priority: 'high', labelIds: [labelA.id], isFavorite: true },
    { title: 'Sans catégorie', status: 'todo', priority: 'low', labelIds: [], isFavorite: false },
  ];
  for (const draft of drafts) expect((await page.request.post(`${server.url}/api/issues`, { data: { projectId: projects[0].id, description: '', ...draft } })).ok()).toBeTruthy();
  await page.reload();
  await expect(app.rows).toHaveCount(4);
  await page.getByRole('button', { name: 'Plus de filtres', exact: true }).click();
  const filter = page.getByRole('dialog', { name: 'Plus de filtres', exact: true });
  await filter.getByRole('checkbox', { name: 'À faire', exact: true }).check();
  await filter.getByRole('checkbox', { name: 'En cours', exact: true }).check();
  await filter.getByRole('checkbox', { name: 'Haute', exact: true }).check();
  await filter.getByRole('checkbox', { name: 'Urgente', exact: true }).check();
  await filter.getByRole('checkbox', { name: 'Interface', exact: true }).check();
  await filter.getByRole('checkbox', { name: 'Données', exact: true }).check();
  await filter.getByRole('button', { name: 'Voir les résultats', exact: true }).click();
  await expect(app.rows).toHaveCount(2);
  await expect(app.row('Cible interface')).toBeVisible();
  await expect(app.row('Cible données')).toBeVisible();
  await page.getByRole('button', { name: /^Plus de filtres/ }).click();
  await filter.getByRole('checkbox', { name: 'Favoris uniquement', exact: true }).check();
  await filter.getByRole('button', { name: 'Voir les résultats', exact: true }).click();
  await expect(app.rows).toHaveCount(1);
  await expect(app.row('Cible interface')).toBeVisible();
  await expect.poll(async () => (await (await page.request.get(`${server.url}/api/settings`)).json()).filters.favoritesOnly).toBe(true);
  await server.restart();
  await page.reload();
  await expect(app.rows).toHaveCount(1);
  await page.getByRole('button', { name: 'Réinitialiser les filtres', exact: true }).click();
  await expect(app.rows).toHaveCount(4);
});

test('affichage : tri, groupement, propriétés, repli et restauration des colonnes', async ({ app, page, server }, testInfo) => {
  await app.createProject('Atlas', 'ATL');
  await app.createProject('Boréal', 'BOR');
  await app.createTicket({ title: 'Zulu', project: 'Atlas' });
  await app.createTicket({ title: 'Alpha', project: 'Atlas' });
  await app.createTicket({ title: 'Milieu', project: 'Boréal' });
  let options = await display(page);
  await options.getByRole('combobox', { name: 'Grouper les tickets', exact: true }).selectOption('none');
  await options.getByRole('combobox', { name: 'Trier par', exact: true }).selectOption('title');
  await options.getByRole('combobox', { name: 'Ordre', exact: true }).selectOption('asc');
  await options.getByRole('checkbox', { name: 'Identifiant', exact: true }).uncheck();
  await options.getByRole('button', { name: 'Terminer', exact: true }).click();
  await expect(app.rows.locator('.issue-title')).toHaveText(['Alpha', 'Milieu', 'Zulu']);
  await expect(app.rows.locator('.issue-identifier')).toHaveCount(0);
  options = await display(page);
  await options.getByRole('combobox', { name: 'Grouper les tickets', exact: true }).selectOption('project');
  await options.getByRole('button', { name: 'Terminer', exact: true }).click();
  await page.getByRole('button', { name: 'Replier Atlas', exact: true }).click();
  await expect(app.row('Alpha')).toHaveCount(0);
  await expect(app.row('Milieu')).toBeVisible();
  await expect.poll(async () => (await (await page.request.get(`${server.url}/api/settings`)).json()).display.collapsedGroups.length).toBe(1);
  await page.reload();
  await expect(page.getByRole('button', { name: 'Déplier Atlas', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Déplier Atlas', exact: true }).click();
  await expect(app.row('Alpha')).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('workspace-list.png'), fullPage: true });
  await app.board();
  await page.getByRole('button', { name: 'Masquer la colonne Terminé', exact: true }).click();
  await expect(app.column('done')).toHaveCount(0);
  await page.getByRole('button', { name: 'Afficher toutes les colonnes', exact: true }).click();
  await expect(app.column('done')).toBeVisible();
});

test('390 px : paramètres, gestion des étiquettes et filtres restent accessibles', async ({ app, page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await app.createProject('Mobile réglages', 'MOBR');
  await app.createTicket({ title: 'Ticket mobile configurable' });
  await settings(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.getByRole('combobox', { name: 'Taille du texte', exact: true }).selectOption('large');
  await page.getByRole('button', { name: 'Enregistrer les préférences', exact: true }).click();
  await expect(page.getByText('Préférences enregistrées.', { exact: true })).toBeVisible();
  await page.getByRole('navigation', { name: 'Sections des paramètres' }).getByRole('button', { name: /^Étiquettes/ }).click();
  await page.getByRole('button', { name: 'Nouvelle étiquette', exact: true }).click();
  const editor = page.getByRole('dialog');
  const bounds = await editor.boundingBox();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390);
  await editor.getByRole('textbox', { name: 'Nom de l’étiquette', exact: true }).fill('Mobile');
  await editor.getByRole('button', { name: 'Créer l’étiquette', exact: true }).click();
  await expect(editor).toBeHidden();
  await tickets(page);
  await page.getByRole('button', { name: 'Plus de filtres', exact: true }).click();
  await expect(page.getByRole('dialog').getByRole('checkbox', { name: 'Mobile', exact: true })).toBeVisible();
  await page.getByRole('dialog').getByRole('button', { name: 'Voir les résultats', exact: true }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: testInfo.outputPath('workspace-mobile.png'), fullPage: true });
});
