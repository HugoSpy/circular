import assert from 'node:assert/strict';
import { createHash, randomUUID } from 'node:crypto';
import { mkdtemp, readFile, readdir, realpath, rm, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { promisify } from 'node:util';
import { execFile } from 'node:child_process';
import { chromium, expect } from '@playwright/test';

const run = promisify(execFile);
const origin = 'http://127.0.0.1:8000';
const external = 'https://example.org/atelier?q=1#programme';
const circular = 'https://circular.example/tickets/42';
const thresholds = { search: 1000, zip: 5000 };
const samples = 20;
const warmups = 2;

function summary(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const at = fraction => sorted[Math.ceil(fraction * sorted.length) - 1];
  return Object.fromEntries(Object.entries({
    min: sorted[0], mediane: at(0.5), p95: at(0.95), max: sorted.at(-1),
  }).map(([label, value]) => [label, Number(value.toFixed(1))]));
}

async function seed(page) {
  async function write(method, route, data) {
    const response = await page.request.fetch(route, { method, headers: { Origin: origin }, data });
    assert.ok(response.ok(), `${method} ${route} : ${response.status()} ${await response.text()}`);
    return response.json();
  }

  const space = await write('POST', '/api/workspaces', { name: 'Recette locale — Forum fictif' });
  const add = (title, parentId) => write('POST', `/api/workspaces/${space.id}/pages`, { title, parentId });
  const roots = [], sections = [], leaves = [];
  for (let index = 0; index < 5; index++) roots.push(await add(`Pôle recette ${index + 1}`));
  for (let index = 0; index < 25; index++) {
    const title = index < 2 ? 'Été : Inscriptions ?' : `Section recette ${index + 1}`;
    sections.push(await add(title, roots[index % roots.length].id));
  }
  for (let index = 0; index < 70; index++) {
    leaves.push(await add(`Fiche mesure ${String(index + 1).padStart(3, '0')}`, sections[index % sections.length].id));
  }

  let bytes = 0;
  for (const [index, document] of [...roots, ...sections, ...leaves].entries()) {
    const paragraphs = Array.from({ length: 80 }, (_, paragraph) => {
      const reference = createHash('sha256').update(`${index}/${paragraph}`).digest('hex');
      return `Décision fictive ${paragraph + 1}. Vérifier les inscriptions et le programme. Code de suivi ${reference.slice(0, 40)}.\n\n`;
    });
    let markdown = paragraphs.join('');
    if (document.id === sections[0].id) markdown = `[Aller](/pages/${sections[1].id}) [Ticket](${circular})\n\n` + markdown;
    if (document.id === sections[1].id) markdown = `[Retour](/pages/${sections[0].id}) [Atelier](${external})\n\n` + markdown;
    await write('PATCH', `/api/pages/${document.id}`, { markdown, requestId: randomUUID(), expectedRevision: 1 });
    bytes += Buffer.byteLength(markdown, 'utf8');
  }
  return { space, sections, leaves, bytes };
}

async function verifyArchive(file, sections) {
  const dir = await mkdtemp(join(tmpdir(), 'circular-recette-zip.'));
  try {
    await run('unzip', ['-tqq', file]);
    await run('unzip', ['-qq', file, '-d', dir]);
    const paths = (await readdir(dir, { recursive: true })).filter(path => path.endsWith('.md'));
    assert.equal(paths.length, 100);
    const [first, second] = sections.slice(0, 2).map(section => {
      const path = paths.find(name => name.endsWith(`-${section.id.slice(0, 8)}.md`));
      assert.ok(path?.includes('Été'));
      return join(dir, path);
    });
    for (const [source, target, label, url] of [[first, second, 'Aller', circular], [second, first, 'Retour', external]]) {
      const body = await readFile(source, 'utf8');
      const href = body.match(new RegExp(`\\[${label}\\]\\(([^)]+)\\)`))?.[1];
      assert.ok(href);
      assert.equal(await realpath(resolve(dirname(source), decodeURIComponent(href))), await realpath(target));
      assert.ok(body.includes(`](${url})`));
    }
    return paths.length;
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

const browser = await chromium.launch();
try {
  const desktop = await browser.newPage({ baseURL: origin, viewport: { width: 1440, height: 960 } });
  // Ce point d’entrée provient de tests.browser_app. Exécuter sur un serveur de recette neuf.
  await desktop.goto('/test-forge/select/alpha');
  await desktop.getByRole('link', { name: 'Continuer avec Forge ID' }).click();
  await expect(desktop.getByRole('heading', { name: 'Mes espaces' })).toBeVisible();
  const { space, sections, leaves, bytes } = await seed(desktop);
  const desktopState = await desktop.context().storageState();
  const mobile = await browser.newPage({ baseURL: origin, viewport: { width: 390, height: 844 }, storageState: desktopState });
  const results = [];
  let archiveProof;

  for (const [viewport, page] of [[1440, desktop], [390, mobile]]) {
    const search = [], zip = [];
    await page.goto('/recherche');
    const field = page.getByRole('searchbox', { name: 'Rechercher dans les espaces' });
    for (const [index, document] of leaves.slice(0, warmups + samples).entries()) {
      const started = performance.now();
      await field.fill(document.title);
      await expect(page.locator(`a[href="/pages/${document.id}"]`)).toBeVisible();
      if (index >= warmups) search.push(performance.now() - started);
    }

    await page.goto('/espaces/' + space.id);
    const button = page.getByRole('button', { name: 'Télécharger le ZIP Markdown' });
    await expect(button).toBeEnabled();
    for (let index = 0; index < warmups + samples; index++) {
      const started = performance.now();
      const pending = page.waitForEvent('download');
      await button.click();
      const download = await pending;
      try {
        const path = await download.path();
        const elapsed = performance.now() - started;
        if (index >= warmups) zip.push(elapsed);
        if (!archiveProof) {
          archiveProof = { fichiers: await verifyArchive(path, sections), octets: (await stat(path)).size };
        }
      } finally {
        await download.delete();
      }
    }
    results.push({ largeur_px: viewport, recherche_ms: summary(search), zip_ms: summary(zip) });
  }
  console.log(JSON.stringify({ pages: 100, niveaux: 3, source_octets: bytes, echantillons: samples,
    prechauffages: warmups, seuils_ms: thresholds, archive: archiveProof, resultats: results }, null, 2));
  assert.ok(results.every(result => result.recherche_ms.p95 <= thresholds.search && result.zip_ms.p95 <= thresholds.zip),
    'Un seuil de performance locale est dépassé.');
} finally {
  await browser.close();
}
