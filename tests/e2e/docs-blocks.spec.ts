import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';

async function openBlankPage(page: Page) {
  await page.getByRole('button', { name: 'Docs', exact: true }).click();
  await page.getByRole('main').getByRole('button', { name: 'Nouvelle page', exact: true }).click();
  const form = page.getByRole('dialog', { name: 'Nouvelle page', exact: true });
  await form.getByRole('textbox', { name: 'Titre', exact: true }).fill('Page à composer');
  await form.getByRole('button', { name: 'Créer la page', exact: true }).click();
  const editor = page.getByRole('textbox', { name: 'Contenu de la page', exact: true });
  await expect(editor).toBeVisible();
  await expect(editor).toBeEmpty();
  await editor.click();
  return editor;
}

async function readSavedMarkdown(page: Page) {
  const url = new URL(page.url());
  const workspaces = await page.request.get(url.origin + '/api/workspaces');
  expect(workspaces.ok()).toBeTruthy();
  const workspace = ((await workspaces.json()) as { slug: string; id: number }[])
    .find(item => item.slug === url.searchParams.get('workspace'));
  expect(workspace).toBeDefined();
  const response = await page.request.get(url.origin + `/api/workspaces/${workspace!.id}/docs/pages/${url.searchParams.get('docs')}`);
  expect(response.ok()).toBeTruthy();
  return (await response.json()).markdown as string;
}

test('le menu de blocs s’utilise au clavier et le titre est enregistré en Markdown', async ({ app, page }) => {
  const editor = await openBlankPage(app.page);
  const list = page.getByRole('listbox', { name: 'Types de bloc' });
  const menu = page.getByRole('region', { name: 'Commandes d’insertion' });

  await page.keyboard.type('/');
  await expect(list.getByRole('option')).toHaveCount(13);
  await expect(list.getByRole('option', { name: 'Vue de collection', exact: true })).toBeVisible();
  await expect(list.getByRole('option', { name: 'Texte', exact: true })).toHaveAttribute('aria-selected', 'true');
  await page.keyboard.press('ArrowDown');
  const title = list.getByRole('option', { name: 'Titre', exact: true });
  await expect(title).toHaveAttribute('aria-selected', 'true');
  await expect(editor).toHaveAttribute('aria-activedescendant', (await title.getAttribute('id'))!);
  await page.keyboard.type('tit');
  await expect(list.getByRole('option')).toHaveCount(1);
  await page.keyboard.press('Enter');
  await expect(menu).toHaveCount(0);
  await expect(editor.getByRole('heading', { level: 2 })).toBeVisible();
  await page.keyboard.press('ControlOrMeta+z');
  await expect(editor.getByRole('heading', { level: 2 })).toHaveCount(0);
  await expect(editor).toHaveText('/tit');
  await page.keyboard.press('ControlOrMeta+Shift+z');
  const insertedTitle = editor.getByRole('heading', { level: 2 });
  await expect(insertedTitle).toBeVisible();
  await insertedTitle.click();
  await page.keyboard.insertText('Mon titre persistant');
  await expect(insertedTitle).toHaveText('Mon titre persistant');

  await page.keyboard.press('Enter');
  await page.keyboard.type('/introuvable');
  await expect(menu.getByRole('status')).toHaveText('Aucun bloc trouvé.');
  await page.keyboard.press('Escape');
  await expect(menu).toHaveCount(0);
  await expect(editor).toBeFocused();
  await expect(editor).toContainText('/introuvable');

  await page.keyboard.press('Enter');
  await page.keyboard.type('https://exemple.test/a/b');
  await expect(menu).toHaveCount(0);

  await page.keyboard.press('Enter');
  await page.keyboard.type('/code');
  await list.getByRole('option', { name: 'Bloc de code', exact: true }).click();
  await expect(editor.locator('pre')).toBeVisible();
  await page.keyboard.type('/literal');
  await expect(menu).toHaveCount(0);

  const saved = '## Mon titre persistant\n\n/introuvable\n\nhttps://exemple.test/a/b\n\n```\n/literal\n```';
  await expect.poll(async () => (await readSavedMarkdown(page)).trimEnd()).toBe(saved);
  await page.reload();
  await expect(editor.getByRole('heading', { name: 'Mon titre persistant', level: 2 })).toBeVisible();
  await expect(editor.locator('pre')).toHaveText('/literal');

  await page.getByRole('button', { name: 'Markdown', exact: true }).click();
  const source = page.getByRole('textbox', { name: 'Source Markdown' });
  await expect.poll(async () => (await source.inputValue()).trimEnd()).toBe(saved);
  await source.fill(saved + '\n\n/tit');
  await expect(menu).toHaveCount(0);
});

test.describe('menu de blocs sur écran tactile', () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test('le choix tactile insère une liste à cocher qui survit au rechargement', async ({ app, page }) => {
    const editor = await openBlankPage(app.page);
    await page.keyboard.type('/tache');
    const choice = page.getByRole('option', { name: 'Liste à cocher', exact: true });
    await expect(choice).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
    await choice.tap();
    await expect(editor.getByRole('checkbox')).toBeVisible();
    await page.keyboard.insertText('Un élément à faire');
    await expect.poll(async () => (await readSavedMarkdown(page)).trimEnd()).toBe('- [ ] Un élément à faire');
    await page.reload();
    await expect(editor.getByRole('checkbox')).toBeVisible();
    await expect(editor).toContainText('Un élément à faire');
  });
});

test('le tableau, l’encadré et le volet survivent au passage par la source Markdown', async ({ app, page }) => {
  const editor = await openBlankPage(app.page);
  await page.getByRole('button', { name: '+ Bloc', exact: true }).click();
  await expect(page.getByRole('option', { name: 'Tableau simple', exact: true })).toBeVisible();
  await page.keyboard.press('Escape');
  await page.keyboard.type('/tableau');
  await page.getByRole('option', { name: 'Tableau simple', exact: true }).click();
  const inserted = editor.getByRole('table');
  await expect(inserted).toBeVisible();
  await expect(inserted.getByRole('columnheader')).toHaveCount(2);

  await page.getByRole('button', { name: 'Markdown', exact: true }).click();
  const source = page.getByRole('textbox', { name: 'Source Markdown' });
  const example = [
    '| Étape | Échéance |', '| :--- | ---: |', '| Carnet \\| règle | Mardi |', '',
    '> [!NOTE] À retenir', '> Préparer le support.', '',
    '> [!NOTE]- Matériel', '> Carnet et feutres.', '',
  ].join('\n');
  await source.fill(example);
  await expect.poll(() => readSavedMarkdown(page)).toBe(example);
  await page.getByRole('button', { name: 'Mode visuel', exact: true }).click();
  await expect(editor.getByRole('table')).toBeVisible();
  await expect(editor.getByRole('cell', { name: 'Carnet | règle' })).toBeVisible();
  await expect(editor.getByText('Préparer le support.')).toBeVisible();
  const fold = editor.locator('details');
  await expect(fold.getByText('Carnet et feutres.')).toBeHidden();
  await fold.locator('summary').click({ position: { x: 4, y: 9 } });
  await expect(fold.getByText('Carnet et feutres.')).toBeVisible();
  await editor.getByRole('textbox', { name: 'Titre du bloc' }).last().fill('Matériel révisé');
  await expect.poll(() => readSavedMarkdown(page)).toContain('> [!NOTE]- Matériel révisé');
  await page.reload();
  await expect(editor.getByRole('table')).toBeVisible();
  await expect(editor.locator('details').getByRole('textbox', { name: 'Titre du bloc' })).toHaveValue('Matériel révisé');
  await expect(editor.getByRole('cell', { name: 'Carnet | règle' })).toBeVisible();
  await page.getByRole('button', { name: 'Markdown', exact: true }).click();
  await expect(source).toHaveValue(/> \[!NOTE\]- Matériel révisé\n> Carnet et feutres/);
});
