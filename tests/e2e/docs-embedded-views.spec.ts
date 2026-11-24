import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';

async function create(page: Page, url: string, data: object) {
  const response = await page.request.post(url, { data });
  expect(response.status()).toBe(201);
  return response.json();
}

test.use({ hasTouch: true });

test('une vue intégrée reflète les données et les réglages de la vue source', async ({ app, page, browser }) => {
  await app.page.getByRole('button', { name: 'Docs', exact: true }).click();
  const main = page.getByRole('main');
  const doc = page.getByRole('textbox', { name: 'Contenu de la page', exact: true });
  const dialog = page.getByRole('dialog');
  const button = (name: string) => main.getByRole('button', { name, exact: true });
  const pane = (name: string) => main.getByRole('region', { name, exact: true });
  const heading = (name: string) => main.getByRole('heading', { name, exact: true, level: 1 });
  const exported = await main.getByRole('link', { name: 'Exporter', exact: true }).getAttribute('href');
  const base = new URL(exported!, page.url()).href.replace(/\/export$/, '');
  const collection = await create(page, base + '/collections', { title: 'Ressources' });
  const collectionUrl = base + '/collections/' + collection.id;
  const field = await create(page, collectionUrl + '/fields', { name: 'État', kind: 'select', options: ['À relire', 'Prêt'] });
  const guide = await create(page, base + '/pages', { title: 'Guide de réunion', collectionId: collection.id });
  const another = await create(page, base + '/pages', { title: 'Trame d’atelier', collectionId: collection.id });
  const other = await create(page, base + '/pages', { title: 'Fiche prête', collectionId: collection.id });
  for (const [id, value] of [[guide.id, 'À relire'], [another.id, 'À relire'], [other.id, 'Prêt']]) {
    expect((await page.request.patch(base + '/pages/' + id + '/properties/' + field.id, { data: { value } })).ok()).toBeTruthy();
  }
  const saved = {
    name: 'Revue', layout: 'table', hidden: [field.id], sorts: [{ fieldId: 'title', direction: 'desc' }],
    filterTree: { mode: 'all', conditions: [{ fieldId: field.id, operator: 'eq', value: 'À relire' }] },
  };
  const view = await create(page, collectionUrl + '/views', saved);
  const empty = await create(page, base + '/collections', { title: 'Bibliothèque vide' });
  await page.reload();
  await button('Nouvelle page').click();
  await dialog.getByRole('textbox', { name: 'Titre', exact: true }).fill('Carnet d’atelier');
  await dialog.getByRole('button', { name: 'Créer la page', exact: true }).click();
  await expect(heading('Carnet d’atelier')).toBeVisible();
  const host = page.url();
  const hostApi = base + '/pages/' + new URL(host).searchParams.get('docs');

  async function pick(collectionName: string, viewName: string) {
    await expect(dialog.getByRole('combobox', { name: 'Collection', exact: true })).toBeFocused();
    await dialog.getByRole('combobox', { name: 'Collection', exact: true }).selectOption({ label: collectionName });
    await dialog.getByRole('combobox', { name: 'Vue enregistrée', exact: true }).selectOption({ label: viewName });
    await dialog.getByRole('button', { name: 'Insérer la vue', exact: true }).click();
  }

  await doc.fill('/vue');
  await doc.press('Enter');
  await dialog.getByRole('button', { name: 'Annuler', exact: true }).click();
  await expect(doc).toHaveText('/vue');
  await doc.fill('/vue de');
  await doc.press('Enter');
  await pick('Ressources', 'Revue');
  const preview = pane('Revue');
  const expected = ['Trame d’atelier', 'Guide de réunion'];
  await expect(preview.getByRole('table').getByRole('link')).toHaveText(expected);
  await expect(preview.getByRole('columnheader', { name: 'État', exact: true })).toHaveCount(0);
  await expect.poll(async () => (await (await page.request.get(hostApi)).json()).markdown).toContain(
    '/collections/' + collection.id + '/views/' + view.id,
  );
  const markdown = (await (await page.request.get(hostApi)).json()).markdown;
  const second = await create(page, base + '/pages', { title: 'Deuxième page' });
  const secondUrl = new URL(host);
  secondUrl.searchParams.set('docs', second.id);
  expect((await page.request.patch(base + '/pages/' + second.id + '/body', { data: { markdown, revision: 1 } })).ok()).toBeTruthy();

  await preview.getByRole('link', { name: 'Ouvrir la vue', exact: true }).click();
  await expect(heading('Ressources')).toBeVisible();
  await expect(button('Revue')).toHaveAttribute('aria-pressed', 'true');
  await page.reload();
  await expect(button('Revue')).toHaveAttribute('aria-pressed', 'true');
  await expect(main.getByRole('table').getByRole('link')).toHaveText(expected);
  expect(new URL(page.url()).searchParams.get('docView')).toBe(view.id);
  expect((await page.request.patch(collectionUrl + '/views/' + view.id, {
    data: { ...saved, name: 'Vue mise à jour', hidden: [], layout: 'list', filterTree: { mode: 'all', conditions: [] } },
  })).ok()).toBeTruthy();
  for (const address of [host, secondUrl.href]) {
    await page.goto(address);
    const list = pane('Vue mise à jour').getByRole('list');
    await expect(list.getByRole('link')).toHaveText([...expected, 'Fiche prête']);
  }

  expect((await page.request.patch(collectionUrl + '/views/' + view.id, {
    data: { ...saved, name: 'Suivi', layout: 'board', groupBy: field.id, filterTree: { mode: 'all', conditions: [] } },
  })).ok()).toBeTruthy();
  const profile = await browser.newContext();
  try {
    const participant = await profile.newPage();
    const origin = new URL(host).origin;
    const email = 'lecture-vues@epita.fr';
    expect((await participant.request.post(origin + '/api/auth/register', { data: {
      username: 'Lina Lectrice', email, password: 'Participant-docs-test-2026!',
    } })).status()).toBe(202);
    const verification = await participant.request.get(origin + '/api/test/email-verification?email=' + encodeURIComponent(email));
    const signedIn = await participant.request.post(origin + '/api/auth/verification/confirm', { data: await verification.json() });
    expect(signedIn.status()).toBe(200);
    const session = await signedIn.json();
    const invitation = await create(page, base.replace(/\/docs$/, '/invitations'), { email });
    expect((await participant.request.post(origin + '/api/workspace-invitations/' + invitation.id + '/accept', {
      data: {}, headers: { 'X-CSRF-Token': session.csrfToken },
    })).ok()).toBeTruthy();
    expect((await page.request.patch(base + '/access/' + session.user.id, { data: { role: 'reader' } })).ok()).toBeTruthy();
    await participant.goto(host);
    const readOnly = participant.getByRole('region', { name: 'Suivi', exact: true });
    await expect(readOnly.getByRole('region', { name: 'Colonnes du kanban' })).toBeVisible();
    await expect(readOnly.getByRole('link', { name: 'Fiche prête', exact: true })).toBeVisible();
    await expect(readOnly.getByRole('button')).toHaveCount(0);
    await readOnly.getByRole('link', { name: 'Ouvrir la vue', exact: true }).click();
    await expect(participant.getByRole('button', { name: 'Suivi', exact: true })).toHaveAttribute('aria-pressed', 'true');
  } finally {
    await profile.close();
  }

  await page.goto(host);
  await page.setViewportSize({ width: 390, height: 844 });
  await button('+ Bloc').tap();
  await page.getByRole('option', { name: 'Vue de collection', exact: true }).tap();
  await pick(empty.title, 'Toutes les pages');
  await expect(pane('Toutes les pages')).toContainText('Cette collection est vide.');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  expect((await page.request.delete(collectionUrl + '/views/' + view.id)).status()).toBe(204);
  await page.reload();
  await expect(pane('Vue indisponible')).toBeVisible();
  await button('Retirer le bloc Vue indisponible').tap();
  await expect(pane('Vue indisponible')).toHaveCount(0);
  await expect.poll(async () => (await (await page.request.get(hostApi)).json()).markdown).not.toContain(view.id);
});
