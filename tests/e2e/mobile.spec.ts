import path from 'node:path';
import { test, expect } from './fixtures';
import { root } from '../../scripts/python-path.mjs';

test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

test('écran 390 px : création, détail et changement de statut restent utilisables', async ({ app, page }) => {
  await app.createProject('Mobilité', 'MOB');
  await app.createTicket({ title: 'Un ticket depuis le téléphone', description: 'Description mobile.', priority: 'medium' });
  await expect(app.row('Un ticket depuis le téléphone')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await app.openTicket('Un ticket depuis le téléphone');
  const bounds = await app.detail.boundingBox();
  expect(bounds).not.toBeNull();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390);
  const saved = page.waitForResponse(response => /\/api\/issues\/\d+$/.test(response.url()) && response.request().method() === 'PATCH');
  await app.saveTicket({ title: 'Un ticket depuis le téléphone', status: 'in_progress' });
  expect((await saved).ok()).toBeTruthy();
  await app.closeDetail();
  await app.board();
  await expect(app.column('in_progress').getByText('Un ticket depuis le téléphone', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await app.card('Un ticket depuis le téléphone').scrollIntoViewIfNeeded();
  await expect(app.card('Un ticket depuis le téléphone')).toBeInViewport();
  await page.screenshot({ path: path.join(root, '.test-data', 'mobile-checkpoint.png'), fullPage: true });
});
