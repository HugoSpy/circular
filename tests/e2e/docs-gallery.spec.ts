import { expect, test } from './fixtures';

async function create(page: import('@playwright/test').Page, url: string, data: object) {
  const response = await page.request.post(url, { data });
  expect(response.status()).toBe(201);
  return response.json();
}

test('la Galerie réutilise filtres et tris, protège les aperçus et reste accessible sur mobile', async ({ page, app }) => {
  await app.page.getByRole('button', { name: 'Docs', exact: true }).click();
  const main = page.getByRole('main');
  const exportHref = await main.getByRole('link', { name: 'Exporter', exact: true }).getAttribute('href');
  const base = new URL(exportHref!, page.url()).href.replace(/\/export$/, '');
  const collection = await create(page, base + '/collections', { title: 'Collection Galerie' });
  const collectionUrl = base + '/collections/' + collection.id;
  const state = await create(page, collectionUrl + '/fields', { name: 'État', kind: 'select', options: ['En cours', 'À faire'] });
  const priority = await create(page, collectionUrl + '/fields', { name: 'Priorité', kind: 'number' });
  const records = await Promise.all(['Zèbre', 'Alpha', 'Exclue', 'Image perdue'].map(title =>
    create(page, base + '/pages', { title, collectionId: collection.id })));
  const [zebra, alpha, excluded, lost] = records;
  const set = async (entry: { id: string }, field: { id: string }, value: unknown) => {
    expect((await page.request.patch(base + '/pages/' + entry.id + '/properties/' + field.id, { data: { value } })).ok()).toBeTruthy();
  };
  for (const entry of [zebra, alpha, excluded, lost]) await set(entry, state, entry === excluded ? 'À faire' : 'En cours');
  await set(zebra, priority, 3); await set(alpha, priority, 1); await set(excluded, priority, 0); await set(lost, priority, 2);

  const pixel = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jcWQAAAAASUVORK5CYII=', 'base64');
  const assetId = crypto.randomUUID();
  const upload = await page.request.post(base + '/pages/' + zebra.id + '/attachments', {
    params: { assetId, name: 'Plan.png', image: 'true' }, data: pixel,
    headers: { 'Content-Type': 'application/octet-stream' },
  });
  expect(upload.status()).toBe(201);
  const undecodableId = crypto.randomUUID();
  const undecodable = await page.request.post(base + '/pages/' + lost.id + '/attachments', {
    params: { assetId: undecodableId, name: 'Image-corrompue.jpg', image: 'true' },
    data: Buffer.from([0xff, 0xd8, 0xff, 0x00]), headers: { 'Content-Type': 'application/octet-stream' },
  });
  expect(undecodable.status()).toBe(201);
  const body = async (entry: { id: string }, markdown: string) => {
    expect((await page.request.patch(base + '/pages/' + entry.id + '/body', { data: { markdown, revision: 1 } })).ok()).toBeTruthy();
  };
  await body(zebra, '![Plan *signalétique*](/attachments/' + assetId + ')');
  await body(alpha, 'Aucune image.');
  await body(excluded, '![Image filtrée](/attachments/' + assetId + ')');
  await body(lost, '![Référence perdue](/attachments/' + undecodableId + ')\n\n```md\n![Code](/attachments/' + assetId + ')\n```');

  const address = new URL(page.url());
  address.searchParams.set('docs', collection.id);
  await page.goto(address.href);
  const dialog = page.getByRole('dialog');
  await main.getByRole('button', { name: 'Vue', exact: true }).click();
  await dialog.getByRole('textbox', { name: 'Nom de la vue', exact: true }).fill('Galerie équipe');
  await dialog.getByRole('combobox', { name: 'Présentation', exact: true }).selectOption('gallery');
  await expect(dialog.getByRole('combobox', { name: 'Regrouper par', exact: true })).toHaveCount(0);
  await expect(dialog.getByText('La carte reprend la première image privée du contenu enregistré de la page.', { exact: true })).toBeVisible();
  await dialog.getByRole('button', { name: 'Ajouter un filtre', exact: true }).click();
  await dialog.getByRole('combobox', { name: 'Propriété du filtre', exact: true }).selectOption(state.id);
  await dialog.getByRole('combobox', { name: 'Est égal à', exact: true }).selectOption('En cours');
  await dialog.getByRole('button', { name: 'Ajouter un tri', exact: true }).click();
  await dialog.getByRole('combobox', { name: 'Propriété du tri 1', exact: true }).selectOption(priority.id);
  await dialog.getByRole('combobox', { name: 'Ordre du tri 1', exact: true }).selectOption('asc');
  await dialog.getByRole('checkbox', { name: 'État', exact: true }).uncheck();
  await dialog.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await expect(dialog).toBeHidden();

  const gallery = main.getByRole('region', { name: 'Galerie des pages', exact: true });
  const cards = gallery.locator('.docs-gallery-card');
  await expect(cards).toHaveCount(3);
  await expect(cards.locator('h2 a')).toHaveText(['Alpha', 'Image perdue', 'Zèbre']);
  await expect(cards.nth(0).getByText('Sans image', { exact: true })).toBeVisible();
  await expect(cards.nth(0).getByText('Priorité', { exact: true })).toBeVisible();
  await expect(cards.nth(0).getByText('État', { exact: true })).toHaveCount(0);
  await expect(cards.nth(1).getByRole('img', { name: 'Image indisponible' })).toBeVisible();
  await expect(cards.nth(2).getByRole('img', { name: 'Plan signalétique' })).toBeVisible();
  const preview = cards.nth(2).getByRole('img', { name: 'Plan signalétique' });
  await preview.scrollIntoViewIfNeeded();
  await expect.poll(() => preview.evaluate(image => (image as HTMLImageElement).naturalWidth)).toBe(1);
  await expect(cards.getByRole('link', { name: 'Exclue', exact: true })).toHaveCount(0);

  const saved = await (await page.request.get(collectionUrl)).json();
  const view = saved.views.find((item: { name: string }) => item.name === 'Galerie équipe');
  const reconfigured = await page.request.patch(collectionUrl + '/views/' + view.id, { data: {
    name: view.name, layout: 'gallery', groupBy: null, dateFieldId: null,
    filterTree: { mode: 'all', conditions: [{ fieldId: state.id, operator: 'eq', value: 'En cours' }] },
    sorts: [{ fieldId: priority.id, direction: 'desc' }], hidden: [state.id],
  } });
  expect(reconfigured.ok()).toBeTruthy();
  const secondView = await create(page, collectionUrl + '/views', {
    name: 'Galerie bis', layout: 'gallery', groupBy: null, dateFieldId: null,
    filterTree: { mode: 'all', conditions: [{ fieldId: state.id, operator: 'eq', value: 'En cours' }] },
    sorts: [{ fieldId: priority.id, direction: 'desc' }], hidden: [state.id],
  });
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(main.getByRole('region', { name: 'Galerie des pages', exact: true }).locator('.docs-gallery-card h2 a'))
    .toHaveText(['Zèbre', 'Image perdue', 'Alpha']);
  const host = await create(page, base + '/pages', { title: 'Vue intégrée' });
  expect((await page.request.patch(base + '/pages/' + host.id + '/body', { data: {
    markdown: '[Galerie](/collections/' + collection.id + '/views/' + view.id + ')\n\n[Galerie](/collections/' + collection.id + '/views/' + secondView.id + ')', revision: 1,
  } })).ok()).toBeTruthy();
  const hostAddress = new URL(page.url());
  hostAddress.searchParams.set('docs', host.id);
  await page.goto(hostAddress.href);
  const embeddedViews = main.getByRole('region', { name: 'Galerie équipe', exact: true });
  await expect(embeddedViews).toHaveCount(1);
  const secondEmbeddedView = main.getByRole('region', { name: 'Galerie bis', exact: true });
  await expect(secondEmbeddedView).toHaveCount(1);
  const embedded = secondEmbeddedView.getByRole('region', { name: 'Galerie des pages', exact: true });
  await expect(embeddedViews.nth(0).locator('.docs-gallery-card h2 a')).toHaveText(['Zèbre', 'Image perdue', 'Alpha']);
  await expect(embedded.locator('.docs-gallery-card h2 a')).toHaveText(['Zèbre', 'Image perdue', 'Alpha']);
  const embeddedAlpha = embedded.getByRole('link', { name: 'Alpha', exact: true });
  await embeddedAlpha.focus();
  await embeddedAlpha.press('Enter');
  await expect(main.getByRole('heading', { name: 'Alpha', exact: true })).toBeVisible();
  const returnEmbedded = main.getByRole('button', { name: 'Retour à la vue intégrée', exact: true });
  await returnEmbedded.click();
  await expect(main.getByRole('region', { name: 'Galerie bis', exact: true })).toHaveCount(1);
  await expect.poll(() => new URL(page.url()).searchParams.get('docView')).toBeNull();
  await expect(main.getByRole('region', { name: 'Galerie bis', exact: true })
    .getByRole('link', { name: 'Alpha', exact: true })).toBeFocused();
  await expect(main.locator('[data-doc-embedded-index="1"][data-doc-embedded-view-id="' + secondView.id + '"]'))
    .toHaveCount(1);
  await main.getByRole('region', { name: 'Galerie bis', exact: true })
    .getByRole('link', { name: 'Alpha', exact: true }).press('Enter');
  await expect(main.getByRole('heading', { name: 'Alpha', exact: true })).toBeVisible();
  const hostRecord = await (await page.request.get(base + '/pages/' + host.id)).json();
  expect((await page.request.patch(base + '/pages/' + host.id + '/body', { data: {
    markdown: '[Galerie remplacée](/collections/' + collection.id + '/views/' + view.id + ')\n\n'
      + '[Galerie remplacée](/collections/' + collection.id + '/views/' + view.id + ')',
    revision: hostRecord.revision,
  } })).ok()).toBeTruthy();
  await main.getByRole('button', { name: 'Retour à la vue intégrée', exact: true }).click();
  await expect(main.getByRole('heading', { name: 'Vue intégrée', exact: true })).toBeVisible();
  const replacementGallery = main.locator('[data-doc-embedded-index="1"][data-doc-embedded-view-id="' + view.id + '"]')
    .getByRole('region', { name: 'Galerie des pages', exact: true });
  await expect(replacementGallery.getByRole('link', { name: 'Alpha', exact: true })).not.toBeFocused();
  await expect(main.getByRole('heading', { name: 'Vue intégrée', exact: true })).toBeFocused();
  await page.keyboard.press('Tab');
  const focusAfterTab = await page.evaluate(() => document.activeElement?.outerHTML ?? '');
  expect(focusAfterTab).not.toBe('');
  await main.getByRole('region', { name: 'Galerie équipe', exact: true }).nth(1)
    .locator('.docs-gallery-preview').first().evaluate(element => {
      const marker = document.createElement('span'); marker.hidden = true;
      element.append(marker); marker.remove();
    });
  await expect.poll(() => page.evaluate(() => document.activeElement?.outerHTML ?? '')).toBe(focusAfterTab);
  await main.getByRole('region', { name: 'Galerie équipe', exact: true }).nth(1)
    .getByRole('link', { name: 'Ouvrir la vue', exact: true }).click();
  await expect.poll(() => new URL(page.url()).searchParams.get('docView')).toBe(view.id);
  await expect(main.getByRole('region', { name: 'Galerie des pages', exact: true }).locator('.docs-gallery-card h2 a'))
    .toHaveText(['Zèbre', 'Image perdue', 'Alpha']);

  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  const galleryLink = main.getByRole('region', { name: 'Galerie des pages', exact: true }).getByRole('link', { name: 'Alpha', exact: true });
  await galleryLink.focus();
  await galleryLink.press('Enter');
  await expect(main.getByRole('heading', { name: 'Alpha', exact: true })).toBeVisible();
  const returnCollection = main.getByRole('button', { name: 'Retour à la galerie', exact: true });
  await returnCollection.click();
  const returnedGallery = main.getByRole('region', { name: 'Galerie des pages', exact: true });
  await expect(returnedGallery.getByRole('link', { name: 'Alpha', exact: true })).toBeFocused();
  await returnedGallery.getByRole('link', { name: 'Alpha', exact: true }).press('Enter');
  await expect(main.getByRole('heading', { name: 'Alpha', exact: true })).toBeVisible();
  const filteredView = await page.request.patch(collectionUrl + '/views/' + view.id, { data: {
    name: view.name, layout: 'gallery', groupBy: null, dateFieldId: null,
    filterTree: { mode: 'all', conditions: [{ fieldId: state.id, operator: 'eq', value: 'À faire' }] },
    sorts: [{ fieldId: priority.id, direction: 'desc' }], hidden: [state.id],
  } });
  expect(filteredView.ok()).toBeTruthy();
  await main.getByRole('button', { name: 'Retour à la galerie', exact: true }).click();
  await expect(main.getByRole('heading', { name: 'Collection Galerie', exact: true })).toBeFocused();
  const excludingGallery = main.getByRole('region', { name: 'Galerie des pages', exact: true });
  await expect(excludingGallery.getByRole('link', { name: 'Alpha', exact: true })).toHaveCount(0);
  const restoredView = await page.request.patch(collectionUrl + '/views/' + view.id, { data: {
    name: view.name, layout: 'gallery', groupBy: null, dateFieldId: null,
    filterTree: { mode: 'all', conditions: [{ fieldId: state.id, operator: 'eq', value: 'En cours' }] },
    sorts: [{ fieldId: priority.id, direction: 'desc' }], hidden: [state.id],
  } });
  expect(restoredView.ok()).toBeTruthy();
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(main.getByRole('region', { name: 'Galerie des pages', exact: true }).getByRole('link', { name: 'Alpha', exact: true })).toBeVisible();
  const alphaRecord = await (await page.request.get(base + '/pages/' + alpha.id)).json();
  const trashed = await page.request.post(base + '/pages/' + alpha.id + '/trash', { data: { revision: alphaRecord.revision } });
  expect(trashed.status()).toBe(201);
  const trashOperation = await trashed.json();
  const sourceAddress = new URL(page.url());
  sourceAddress.searchParams.set('docs', collection.id);
  sourceAddress.searchParams.set('docView', view.id);
  await page.goto(sourceAddress.href);
  await expect(main.getByRole('region', { name: 'Galerie des pages', exact: true }).getByRole('link', { name: 'Alpha', exact: true })).toHaveCount(0);
  const restored = await page.request.post(base + '/trash/' + trashOperation.id + '/restore', { data: {} });
  expect(restored.status()).toBe(200);
  await page.reload();
  await expect(main.getByRole('region', { name: 'Galerie des pages', exact: true }).getByRole('link', { name: 'Alpha', exact: true })).toBeVisible();
});

test('le retour attend un index frais et respecte les interactions pendant le chargement', async ({ page, app }) => {
  await app.page.getByRole('button', { name: 'Docs', exact: true }).click();
  const main = page.getByRole('main');
  const exportHref = await main.getByRole('link', { name: 'Exporter', exact: true }).getAttribute('href');
  const base = new URL(exportHref!, page.url()).href.replace(/\/export$/, '');
  const basePath = new URL(base).pathname;
  const collection = await create(page, base + '/collections', { title: 'Retour asynchrone' });
  const collectionUrl = base + '/collections/' + collection.id;
  const state = await create(page, collectionUrl + '/fields', { name: 'État', kind: 'select', options: ['Actif', 'Archivé'] });
  const alpha = await create(page, base + '/pages', { title: 'Alpha', collectionId: collection.id });
  const updateState = (value: string) => page.request.patch(base + '/pages/' + alpha.id + '/properties/' + state.id, { data: { value } });
  expect((await updateState('Actif')).ok()).toBeTruthy();
  const view = await create(page, collectionUrl + '/views', {
    name: 'Galerie de retour', layout: 'gallery', groupBy: null, dateFieldId: null,
    filterTree: { mode: 'all', conditions: [{ fieldId: state.id, operator: 'eq', value: 'Actif' }] },
    sorts: [], hidden: [],
  });
  const address = new URL(page.url());
  address.searchParams.set('docs', collection.id);
  address.searchParams.set('docView', view.id);
  await page.goto(address.href);
  const gallery = main.getByRole('region', { name: 'Galerie des pages', exact: true });
  const alphaLink = gallery.getByRole('link', { name: 'Alpha', exact: true });
  await expect(alphaLink).toBeVisible();
  await alphaLink.focus();
  await alphaLink.press('Enter');
  await expect(main.getByRole('heading', { name: 'Alpha', exact: true })).toBeVisible();

  expect((await updateState('Archivé')).ok()).toBeTruthy();
  let releaseIndex = () => {};
  let indexStarted = false;
  const indexGate = new Promise<void>(resolve => { releaseIndex = resolve; });
  await page.route(url => url.pathname === basePath && url.search === '', async route => {
    if (route.request().method() === 'GET') {
      indexStarted = true;
      await indexGate;
    }
    await route.continue();
  });
  await main.getByRole('button', { name: 'Retour à la galerie', exact: true }).click();
  await expect.poll(() => indexStarted).toBe(true);
  await expect(gallery.getByRole('link', { name: 'Alpha', exact: true })).toBeVisible();
  await expect(main.getByRole('heading', { name: 'Retour asynchrone', exact: true })).toBeFocused();
  await expect(gallery.getByRole('link', { name: 'Alpha', exact: true })).not.toBeFocused();
  releaseIndex();
  await expect(gallery.getByRole('link', { name: 'Alpha', exact: true })).toHaveCount(0);
  await expect(main.getByRole('heading', { name: 'Retour asynchrone', exact: true })).toBeFocused();
  await page.unrouteAll();

  expect((await updateState('Actif')).ok()).toBeTruthy();
  await page.reload();
  await expect(main.getByRole('region', { name: 'Galerie des pages', exact: true })
    .getByRole('link', { name: 'Alpha', exact: true })).toBeVisible();
  await main.getByRole('region', { name: 'Galerie des pages', exact: true })
    .getByRole('link', { name: 'Alpha', exact: true }).press('Enter');
  await expect(main.getByRole('heading', { name: 'Alpha', exact: true })).toBeVisible();

  let releaseBoth = () => {};
  let indexPending = false;
  let collectionPending = false;
  const bothGates = new Promise<void>(resolve => { releaseBoth = resolve; });
  const collectionPath = new URL(collectionUrl).pathname;
  await page.route(url => url.pathname === basePath || url.pathname === collectionPath, async route => {
    if (route.request().method() === 'GET') {
      if (route.request().url().includes('/collections/')) collectionPending = true;
      else indexPending = true;
      await bothGates;
    }
    await route.continue();
  });
  await main.getByRole('button', { name: 'Retour à la galerie', exact: true }).click();
  await expect.poll(() => indexPending).toBe(true);
  await expect.poll(() => collectionPending).toBe(true);
  await page.getByRole('button', { name: 'Docs', exact: true }).focus();
  await page.keyboard.press('Tab');
  await expect(page.locator(':focus')).toHaveRole('button');
  const focusedBeforeLoad = await page.evaluate(() => document.activeElement?.outerHTML ?? '');
  expect(focusedBeforeLoad).not.toBe('');
  releaseBoth();
  await expect(main.getByRole('heading', { name: 'Retour asynchrone', exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.activeElement?.outerHTML ?? '')).toBe(focusedBeforeLoad);
});
