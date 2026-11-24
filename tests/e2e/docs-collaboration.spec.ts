import { expect, test } from './fixtures';

test('un membre en lecture reçoit une mention puis perd le document lors du retrait', async ({ app, page, browser, server }) => {
  const main = page.getByRole('main');
  await app.page.getByRole('button', { name: 'Docs', exact: true }).click();
  await main.getByRole('button', { name: 'Nouvelle page', exact: true }).click();
  const create = page.getByRole('dialog', { name: 'Nouvelle page', exact: true });
  await create.getByRole('textbox', { name: 'Titre', exact: true }).fill('Guide de collaboration');
  await create.getByRole('button', { name: 'Créer la page', exact: true }).click();
  await expect(main.getByRole('heading', { name: 'Guide de collaboration' })).toBeVisible();
  const editor = main.getByRole('textbox', { name: 'Contenu de la page', exact: true });
  await editor.fill('Les ressources privées de l’atelier.');
  await expect(main.getByRole('status').filter({ hasText: /^Enregistré$/ })).toBeVisible();

  const link = page.url();
  const exportHref = await main.getByRole('link', { name: 'Exporter', exact: true }).getAttribute('href');
  expect(exportHref).toBeTruthy();
  const spacePath = exportHref!.split('/').slice(0, 4).join('/');
  const reader = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  try {
    const participant = await reader.newPage();
    const email = 'participant-collaboration@epita.fr';
    const registered = await participant.request.post(server.url + '/api/auth/register', { data: {
      username: 'Camille Lecteur', email, password: 'Participant-docs-test-2026!',
    } });
    expect(registered.status()).toBe(202);
    const verification = await participant.request.get(server.url + '/api/test/email-verification?email=' + encodeURIComponent(email));
    expect(verification.ok()).toBeTruthy();
    const signedIn = await participant.request.post(server.url + '/api/auth/verification/confirm', { data: await verification.json() });
    expect(signedIn.status()).toBe(200);
    const session = await signedIn.json();
    const invite = await page.request.post(server.url + spacePath + '/invitations', { data: { email } });
    expect(invite.status()).toBe(201);
    const join = await participant.request.post(server.url + '/api/workspace-invitations/' + (await invite.json()).id + '/accept', {
      data: {}, headers: { 'X-CSRF-Token': session.csrfToken },
    });
    expect(join.status()).toBe(200);

    await participant.goto(link);
    const participantMain = participant.getByRole('main');
    const participantBody = participantMain.getByRole('textbox', { name: 'Contenu de la page' });
    await expect(participantBody).toBeEditable();

    await main.getByRole('button', { name: 'Accès Docs', exact: true }).click();
    const access = page.getByRole('dialog', { name: /^Accès Docs/ });
    await access.getByRole('combobox', { name: 'Accès Docs de Camille Lecteur', exact: true }).selectOption('reader');
    await expect(access.getByRole('status')).toHaveText('Accès Docs de Camille Lecteur mis à jour.');
    await page.keyboard.press('Escape');
    await expect(main.getByRole('button', { name: 'Accès Docs', exact: true })).toBeFocused();

    await main.getByRole('button', { name: 'Commentaires', exact: true }).press('Enter');
    const discussion = main.getByRole('complementary', { name: 'Commentaires', exact: true });
    await expect(discussion.getByRole('heading', { name: 'Commentaires', exact: true })).toBeFocused();
    await expect(discussion.getByText('Aucun commentaire pour cette page.')).toBeVisible();
    await discussion.getByRole('textbox', { name: 'Votre commentaire' }).fill('Peux-tu relire les ressources ?');
    await discussion.getByRole('combobox', { name: 'Mentionner une personne' }).selectOption({ label: 'Camille Lecteur' });
    await discussion.getByRole('button', { name: 'Publier', exact: true }).click();
    await expect(discussion.getByText('Commentaire publié.')).toBeVisible();

    await participant.evaluate(() => window.dispatchEvent(new Event('focus')));
    await expect(participantMain.getByText('Lecture seule', { exact: true })).toBeVisible();
    await expect(participantBody).toHaveAttribute('aria-readonly', 'true');
    await expect(participantMain.getByRole('button', { name: 'Historique', exact: true })).toHaveCount(0);
    await participantMain.getByRole('button', { name: 'Notifications · non lues', exact: true }).tap();
    const inbox = participant.getByRole('dialog', { name: 'Notifications Docs', exact: true });
    await inbox.getByRole('button', { name: /Non lu.*vous a mentionné/ }).tap();
    const readerDiscussion = participantMain.getByRole('complementary', { name: 'Commentaires', exact: true });
    const comment = readerDiscussion.getByRole('article').filter({ hasText: 'Peux-tu relire les ressources ?' });
    await expect(comment).toBeFocused();
    await expect(readerDiscussion.getByRole('button', { name: 'Publier', exact: true })).toHaveCount(0);
    await expect(participantMain.getByRole('button', { name: 'Notifications', exact: true })).toBeVisible();
    const archive = await participant.request.get(server.url + exportHref);
    expect(archive.status()).toBe(200);
    expect(archive.headers()['content-type']).toBe('application/zip');

    await main.getByRole('button', { name: 'Accès Docs', exact: true }).click();
    await access.getByRole('button', { name: 'Retirer Camille Lecteur de l’espace', exact: true }).click();
    await access.getByRole('button', { name: 'Confirmer le retrait', exact: true }).click();
    await expect(access.getByRole('status')).toHaveText('Camille Lecteur a été retiré de l’espace.');
    await participant.evaluate(() => window.dispatchEvent(new Event('focus')));
    await expect(participantMain.getByRole('heading', { name: 'Document indisponible', exact: true })).toBeVisible();
    await expect(participantBody).toHaveCount(0);
    await expect(readerDiscussion).toHaveCount(0);
    await expect(participantMain.getByRole('button', { name: /Notifications/ })).toHaveCount(0);
    expect((await participant.request.get(server.url + exportHref)).status()).toBe(404);
    await page.keyboard.press('Escape');
    await expect(main.getByText('Les ressources privées de l’atelier.', { exact: true })).toBeVisible();
  } finally {
    await reader.close();
  }
});
