import { readFile } from 'node:fs/promises';
import { expect, test } from './fixtures';

test('un fichier privé survit à la création d’une page depuis un modèle', async ({ app, page, browser, server }) => {
  await app.page.getByRole('button', { name: 'Docs', exact: true }).click();
  const main = page.getByRole('main');
  await main.getByRole('button', { name: 'Nouvelle page', exact: true }).click();
  const create = page.getByRole('dialog', { name: 'Nouvelle page', exact: true });
  await create.getByRole('textbox', { name: 'Titre', exact: true }).fill('Guide de l’atelier');
  await create.getByRole('button', { name: 'Créer la page', exact: true }).click();

  const editor = page.getByRole('textbox', { name: 'Contenu de la page', exact: true });
  await editor.fill('/fichier');
  await page.getByRole('option', { name: 'Fichier', exact: true }).click();
  const form = page.getByRole('dialog', { name: 'Joindre un fichier' });
  const pdf = await readFile('docs/circular-docs/mockups/support-atelier.pdf');
  await form.getByLabel('Fichier local').setInputFiles({ name: 'Support.pdf', mimeType: 'application/pdf', buffer: pdf });
  await form.getByRole('button', { name: 'Insérer', exact: true }).click();
  await expect(editor.getByRole('link', { name: 'Support.pdf' })).toBeVisible();
  await expect(page.getByRole('status').filter({ hasText: /^Enregistré$/ })).toBeVisible();

  await main.getByRole('button', { name: '+ Bloc', exact: true }).click();
  await page.getByRole('option', { name: 'Image', exact: true }).click();
  const imageForm = page.getByRole('dialog', { name: 'Insérer une image' });
  const pixel = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jcWQAAAAASUVORK5CYII=', 'base64');
  await imageForm.getByLabel('Fichier local').setInputFiles({ name: 'Plan.png', mimeType: 'image/png', buffer: pixel });
  await imageForm.getByRole('textbox', { name: 'Texte alternatif' }).fill('Plan de l’atelier');
  await imageForm.getByRole('button', { name: 'Insérer', exact: true }).click();
  const image = editor.getByRole('img', { name: 'Plan de l’atelier' });
  await expect.poll(async () => image.evaluate(element => (element as HTMLImageElement).naturalWidth)).toBe(1);
  await expect(page.getByRole('status').filter({ hasText: /^Enregistré$/ })).toBeVisible();

  await main.getByRole('button', { name: 'Enregistrer comme modèle' }).click();
  const save = page.getByRole('dialog', { name: 'Enregistrer comme modèle' });
  await save.getByRole('textbox', { name: 'Nom du modèle' }).fill('Guide réutilisable');
  await save.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await expect(page.getByText('Modèle enregistré.', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Nouvelle page', exact: true }).click();
  await expect(create.getByRole('combobox', { name: 'Départ' })).toHaveValue('');
  await expect(create.getByRole('option', { name: 'Guide réutilisable' })).toHaveCount(1);
  await create.getByRole('combobox', { name: 'Départ' }).selectOption({ label: 'Guide réutilisable' });
  await create.getByRole('textbox', { name: 'Titre', exact: true }).fill('Atelier du mardi');
  await create.getByRole('button', { name: 'Créer la page', exact: true }).click();
  await expect(main.getByRole('heading', { name: 'Atelier du mardi' })).toBeVisible();
  await page.reload();
  const link = editor.getByRole('link', { name: 'Support.pdf' });
  await expect(link).toBeVisible();
  const [download] = await Promise.all([page.waitForEvent('download'), link.click()]);
  expect(await readFile(await download.path())).toEqual(pdf);
  await expect(image).toBeVisible();

  const href = await link.getAttribute('href');
  expect(href).toBeTruthy();
  const workspaceId = href!.split('/')[3];
  const secondContext = await browser.newContext();
  try {
    const participant = await secondContext.newPage();
    const address = 'participant-docs@epita.fr';
    const registered = await participant.request.post(server.url + '/api/auth/register', { data: {
      username: 'Participant Docs', email: address, password: 'Participant-docs-test-2026!',
    } });
    expect(registered.status()).toBe(202);
    const verification = await participant.request.get(server.url + '/api/test/email-verification?email=' + encodeURIComponent(address));
    expect(verification.ok()).toBeTruthy();
    const signedIn = await participant.request.post(server.url + '/api/auth/verification/confirm', { data: await verification.json() });
    expect(signedIn.ok()).toBeTruthy();
    const session = await signedIn.json();
    const invitation = await page.request.post(server.url + '/api/workspaces/' + workspaceId + '/invitations', {
      data: { email: address },
    });
    expect(invitation.status()).toBe(201);
    const member = await participant.request.post(server.url + '/api/workspace-invitations/' + (await invitation.json()).id + '/accept', {
      data: {}, headers: { 'X-CSRF-Token': session.csrfToken },
    });
    expect(member.ok()).toBeTruthy();
    await participant.goto(server.url);
    const before = await participant.evaluate(async url => {
      const response = await fetch(url);
      return { status: response.status, cache: response.headers.get('cache-control'), bytes: [...new Uint8Array(await response.arrayBuffer())] };
    }, href!);
    expect(before.status).toBe(200);
    expect(before.cache).toContain('no-store');
    expect(Buffer.from(before.bytes)).toEqual(pdf);
    const removed = await page.request.delete(server.url + '/api/workspaces/' + workspaceId + '/members/' + session.user.id);
    expect(removed.status()).toBe(204);
    expect(await participant.evaluate(async url => (await fetch(url)).status, href!)).toBe(404);
    expect(await (await page.request.get(server.url + href)).body()).toEqual(pdf);
  } finally {
    await secondContext.close();
  }
});
