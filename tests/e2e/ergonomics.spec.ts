import path from 'node:path';
import type { Locator, Page } from '@playwright/test';
import { test, expect } from './fixtures';
import { root } from '../../scripts/python-path.mjs';

/** These are usability floors, not snapshots of a particular layout or theme. */
async function expectReadableControl(control: Locator, minimumFont: number, minimumTarget: number) {
  await expect(control).toBeVisible();
  const metrics = await control.evaluate(element => {
    const style = getComputedStyle(element);
    const bounds = element.getBoundingClientRect();
    return { font: Number.parseFloat(style.fontSize), width: bounds.width, height: bounds.height };
  });
  expect(metrics.font, 'Le texte du contrôle doit rester lisible').toBeGreaterThanOrEqual(minimumFont);
  expect(metrics.height, 'Le contrôle doit rester facile à activer').toBeGreaterThanOrEqual(minimumTarget);
  expect(metrics.width, 'Le contrôle doit rester facile à activer').toBeGreaterThanOrEqual(minimumTarget);
}

async function tabTo(page: Page, target: Locator) {
  for (let step = 0; step < 30; step++) {
    await page.keyboard.press('Tab');
    if (await target.evaluate(element => element === document.activeElement)) break;
  }
  await expect(target, 'La commande doit être accessible avec Tab').toBeFocused();
}

test('bureau : commandes lisibles et formulaire accessible au clavier', async ({ app, page }) => {
  await app.createProject('Clarté', 'CLA');
  await app.createTicket({ title: 'Préparer le prochain lancement' });
  await page.reload();
  const createButton = page.getByRole('button', { name: 'Nouveau ticket', exact: true });
  await expect(app.row('Préparer le prochain lancement')).toBeVisible();
  await expect(createButton).toContainText('Nouveau ticket');
  await expect(createButton.getByText('Nouveau ticket', { exact: true })).toBeVisible();
  for (const control of [createButton, app.search, app.projectFilter, app.statusFilter, app.priorityFilter,
    page.getByRole('button', { name: 'Liste', exact: true }), page.getByRole('button', { name: 'Tableau', exact: true })]) {
    await expectReadableControl(control, 12, 32);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await tabTo(page, createButton);
  expect(await createButton.evaluate(element => {
    const style = getComputedStyle(element);
    const outlineVisible = style.outlineStyle !== 'none' && Number.parseFloat(style.outlineWidth) >= 1
      && !['transparent', 'rgba(0, 0, 0, 0)'].includes(style.outlineColor);
    return element.matches(':focus-visible') && (outlineVisible || style.boxShadow !== 'none');
  }), 'Le focus clavier doit posséder un indicateur visible').toBeTruthy();
  await page.keyboard.press('Enter');
  await expect(app.newTicketDialog).toBeVisible();
  await expect(app.newTicketDialog.getByRole('textbox', { name: 'Titre', exact: true })).toBeFocused();

  // Background controls stay inert. Chrome may move Tab to its own toolbar at the boundary.
  for (let step = 0; step < 20; step++) {
    await page.keyboard.press('Tab');
    const focus = await app.newTicketDialog.evaluate(dialog => ({
      inside: dialog.contains(document.activeElement),
      tag: document.activeElement?.tagName,
      name: document.activeElement?.getAttribute('aria-label'),
      pageFocused: document.hasFocus(),
    }));
    expect(focus.inside || (focus.tag === 'BODY' && !focus.pageFocused),
      `Tab ne doit pas atteindre les commandes derrière le dialogue (étape ${step + 1} : ${JSON.stringify(focus)})`).toBeTruthy();
  }
  await tabTo(page, app.newTicketDialog.getByRole('button', { name: 'Fermer', exact: true }));
  await page.keyboard.press('Enter');
  await expect(app.newTicketDialog).toBeHidden();
  await expect(createButton).toBeFocused();
  const ticket = app.row('Préparer le prochain lancement');
  await tabTo(page, ticket);
  await page.keyboard.press('Enter');
  await app.detail.getByRole('button', { name: 'Aller aux commentaires', exact: true }).click();
  const comment = app.detail.getByRole('textbox', { name: 'Ajouter un commentaire', exact: true });
  await expect(comment).toBeFocused();
  await expect(comment).toBeInViewport({ ratio: 1 });
  await page.keyboard.type('Le formulaire de commentaire est accessible directement.');
  await app.detail.getByRole('button', { name: 'Publier le commentaire', exact: true }).click();
  await expect(app.detail.getByText('Le formulaire de commentaire est accessible directement.', { exact: true })).toBeVisible();
  await app.closeDetail();
  await expect(ticket).toBeFocused();
  await page.screenshot({ path: path.join(root, '.test-data', 'redesign-desktop.png'), fullPage: true });
});

test.describe('ergonomie tactile', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  test('390 px : le premier ticket et les commandes restent à portée sans défilement initial', async ({ app, page, server }) => {
    await app.createProject('Prochaines étapes', 'NEXT');
    await app.createTicket({ title: 'Préparer le rendez-vous de lancement', priority: 'high' });
    await page.goto(server.url);
    const ticket = app.row('Préparer le rendez-vous de lancement');
    await expect(ticket).toBeVisible();
    await expect(ticket).toBeInViewport({ ratio: 1 });
    const position = await ticket.boundingBox();
    expect(position).not.toBeNull();
    expect(position!.y, 'Le premier ticket doit rester à portée sous un en-tête compact').toBeLessThan(550);
    expect(position!.y).toBeGreaterThanOrEqual(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();

    const createButton = page.getByRole('button', { name: 'Nouveau ticket', exact: true });
    await expect(createButton).toContainText('Nouveau ticket');
    await expect(createButton.getByText('Nouveau ticket', { exact: true })).toBeVisible();
    for (const control of [createButton, app.search, app.projectFilter, app.statusFilter, app.priorityFilter,
      page.getByRole('button', { name: 'Liste', exact: true }), page.getByRole('button', { name: 'Tableau', exact: true })]) {
      await expectReadableControl(control, 13, 40);
    }
    await page.screenshot({ path: path.join(root, '.test-data', 'redesign-mobile-list.png'), fullPage: true });
    await ticket.tap();
    await expect(app.detail).toBeVisible();
    expect(await app.detail.evaluate(dialog => dialog.scrollWidth <= dialog.clientWidth + 1),
      'Le panneau de détail ne doit pas déborder horizontalement').toBeTruthy();
    for (const control of [app.detail.getByRole('textbox', { name: 'Titre', exact: true }),
      app.detail.getByRole('combobox', { name: 'Statut', exact: true }),
      app.detail.getByRole('combobox', { name: 'Priorité', exact: true })]) {
      await expectReadableControl(control, 13, 40);
    }
    const close = app.detail.getByRole('button', { name: 'Fermer', exact: true });
    const closeBounds = await close.boundingBox();
    expect(closeBounds).not.toBeNull();
    expect(closeBounds!.width).toBeGreaterThanOrEqual(40);
    expect(closeBounds!.height).toBeGreaterThanOrEqual(40);
    await close.tap();
    await expect(app.detail).toBeHidden();
    await expect(ticket).toBeInViewport({ ratio: 1 });
  });
});
