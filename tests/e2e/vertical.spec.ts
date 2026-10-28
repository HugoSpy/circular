import { test, expect } from './fixtures';
import path from 'node:path';
import { root } from '../../scripts/python-path.mjs';

test('tranche verticale : créer un projet et un ticket, puis actualiser', async ({ app, page }) => {
  await app.createProject('Observatoire', 'OBS');
  await app.createTicket({
    title: 'Préparer la première observation',
    description: 'Définir le protocole de démonstration.',
    project: 'Observatoire',
    status: 'todo',
    priority: 'high',
  });
  await expect(page.getByText('Préparer la première observation', { exact: true })).toBeVisible();
  await expect(page.getByText('OBS-1', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText('Préparer la première observation', { exact: true })).toBeVisible();
  await expect(page.getByText('OBS-1', { exact: true })).toBeVisible();
  await page.screenshot({ path: path.join(root, '.test-data', 'vertical-checkpoint.png'), fullPage: true });
});
