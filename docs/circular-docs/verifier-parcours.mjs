import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { chromium, expect } from '@playwright/test';

const docs = 'http://127.0.0.1:8000';
const circular = 'http://127.0.0.1:4316';
const database = process.env.DOCS_TEST_DATABASE_URL;
assert.ok(database, 'Renseigner DOCS_TEST_DATABASE_URL pour la base PostgreSQL de recette.');
const browser = await chromium.launch();

async function send(page, method, url, data, headers, status) {
  const response = await page.request.fetch(url, { method, data, headers });
  assert.equal(response.status(), status, `${method} ${url} : ${await response.text()}`);
  return response.status() === 204 ? undefined : response.json();
}
const call = (page, method, path, data, status = 200) =>
  send(page, method, docs + path, data, { Origin: docs }, status);
const create = (page, path, data) => call(page, 'POST', path, data, 201);
const change = (page, id, expectedRevision, fields, status = 200, requestId = randomUUID()) =>
  call(page, 'PATCH', '/api/pages/' + id, { expectedRevision, requestId, ...fields }, status);
function sql(query) {
  const result = spawnSync('psql', ['-d', database, '-XAt', '-v', 'ON_ERROR_STOP=1', '-c', query], { encoding: 'utf8' });
  if (result.error) throw result.error;
  assert.equal(result.status, 0, result.stderr);
  return result.stdout.trim();
}

async function docsLogin(page, subject) {
  await page.goto(docs + '/test-forge/select/' + subject);
  await page.getByRole('link', { name: 'Continuer avec Forge ID' }).click();
  await expect(page.getByRole('heading', { name: 'Mes espaces' })).toBeVisible();
}

async function circularWorkspace(page, name) {
  const request = (method, path, data, status, headers = {}) => send(page, method, circular + path, data, headers, status);
  const email = name + '@epita.fr';
  await request('POST', '/api/auth/register', { username: name, email, password: 'Une-phrase-fictive-2026!' }, 202);
  const challenge = await request('GET', '/api/test/email-verification?email=' + encodeURIComponent(email), undefined, 200);
  await request('POST', '/api/auth/verification/confirm', challenge, 200);
  const session = await request('GET', '/api/auth/me', undefined, 200);
  const csrf = { 'X-CSRF-Token': session.csrfToken };
  await request('PATCH', '/api/auth/profile', { displayName: name, title: '' }, 200, csrf);
  const { workspace, project } = await request('POST', '/api/workspaces',
    { name: 'Espace ' + name, slug: name, includeWelcomeIssues: false }, 201, csrf);
  const scoped = { ...csrf, 'X-Workspace-Id': String(workspace.id) };
  await request('POST', `/api/workspaces/${workspace.id}/onboarding/complete`, {}, 200, scoped);
  const title = 'Ticket confidentiel de recette';
  const issue = await request('POST', '/api/issues', { title, projectId: project.id }, 201, scoped);
  return { url: `${circular}/?workspace=${workspace.slug}&issue=${issue.id}`, title };
}

async function followTicket(page, url) {
  const link = page.getByRole('link', { name: 'Ticket Circular de recette', exact: true });
  await expect(link).toHaveAttribute('href', url);
  const target = await link.getAttribute('target');
  if (target === '_blank') {
    const opened = page.waitForEvent('popup');
    await link.click();
    return opened;
  }
  await link.click();
  return page;
}

async function scenario(width) {
  const pages = await Promise.all([1, 2, 3].map(() => browser.newPage({ viewport: { width, height: 900 } })));
  const [owner, editor, reader] = pages;
  try {
    const ticket = await circularWorkspace(owner, 'proprio' + width);
    await circularWorkspace(reader, 'lecteur' + width);
    await Promise.all([docsLogin(owner, 'alpha'), docsLogin(editor, 'beta'), docsLogin(reader, 'gamma')]);
    const space = await create(owner, '/api/workspaces', { name: 'Forum fictif ' + width });
    const base = '/api/workspaces/' + space.id;
    const add = (title, parentId) => create(owner, base + '/pages', { title, parentId });
    const first = await add('Pôle inscriptions'), reserve = await add('Pôle logistique');
    const child = await add('Inscriptions', first.id), other = await add('Inscriptions', reserve.id);
    const source = await add('Décisions du forum');
    const revisions = await add('Journal du forum');
    const pagePath = id => '/pages/' + id;
    const apiPath = id => '/api' + pagePath(id);
    const search = '/api/search?q=Décision%20matinale';
    const invite = (email, role) => create(owner, base + '/invitations', { email, role });
    const editorInvite = await invite('beta@epita.fr', 'editor'), readerInvite = await invite('gamma@epita.fr', 'reader');
    await change(owner, source.id, 1, { markdown: `Décision matinale. [Fiche inscriptions](${pagePath(child.id)}) [Ticket Circular de recette](${ticket.url})` });

    const denied = await call(reader, 'GET', apiPath(child.id), undefined, 404);
    assert.deepEqual(denied, await call(reader, 'GET', apiPath(randomUUID()), undefined, 404));
    assert.deepEqual((await call(reader, 'GET', search)).items, []);
    await call(editor, 'POST', '/api/invitations/' + editorInvite.id + '/accept');
    await reader.goto(docs + '/invitations');
    await reader.getByRole('button', { name: 'Accepter', exact: true }).click();
    await expect(reader.getByRole('heading', { name: 'Forum fictif ' + width })).toBeVisible();
    await call(reader, 'GET', apiPath(child.id));
    await change(reader, child.id, 1, { title: 'Modification refusée' }, 403);
    await reader.goto(docs + '/recherche');
    await reader.getByRole('searchbox').fill('DÉCISION MATINALE');
    await expect(reader.getByRole('link', { name: /Décisions du forum/ })).toBeVisible();
    console.log(width, 'partage 404 avant acceptation, lecteur 200 après, écriture 403');

    const matches = await call(editor, 'GET', base + '/link-suggestions?q=Inscriptions');
    assert.equal(matches.items.filter(item => item.title === 'Inscriptions').length, 2);
    await change(editor, child.id, 1, { title: 'Créneaux des inscriptions' });
    await call(editor, 'PATCH', apiPath(child.id), { parentId: reserve.id });
    const moved = await call(reader, 'GET', apiPath(child.id));
    assert.deepEqual(moved.breadcrumb.map(item => item.id), [reserve.id, child.id]);
    assert.equal(sql(`SELECT count(*) FROM page_links WHERE source_id = '${source.id}' AND target_id = '${child.id}'`), '1');
    assert.deepEqual((await call(reader, 'GET', apiPath(other.id) + '/backlinks')).items, []);
    console.log(width, 'homonymes distingués, lien stable, un seul backlink PostgreSQL');

    const setup = await change(owner, revisions.id, 1, { markdown: 'Révision deux' });
    await change(owner, revisions.id, setup.revision, { markdown: 'Révision trois' });
    const writeId = randomUUID();
    await change(owner, revisions.id, 3, { markdown: 'Révision quatre' }, 200, writeId);
    const conflict = await change(editor, revisions.id, 3, { markdown: 'Brouillon concurrent' }, 409);
    assert.equal(conflict.error.latest.revision, 4);
    assert.equal((await change(owner, revisions.id, 3, { markdown: 'Révision quatre' }, 200, writeId)).revision, 4);
    assert.equal(sql(`SELECT string_agg(revision::text, ',' ORDER BY revision) FROM page_revisions WHERE page_id = '${revisions.id}'`), '1,2,3,4');
    console.log(width, 'conflit 409, rejeu, exactement quatre révisions en base');

    const op = await create(editor, apiPath(reserve.id) + '/trash');
    assert.equal(op.count, 3);
    assert.equal(sql(`SELECT count(*) FROM pages WHERE trash_id = '${op.id}'`), '3');
    await reader.goto(docs + pagePath(source.id));
    await expect(reader.getByText('Fiche inscriptions (page indisponible)', { exact: true })).toBeVisible();
    const restored = await call(editor, 'POST', base + '/trash/' + op.id + '/restore');
    assert.equal(restored.count, 3);
    await call(owner, 'PATCH', apiPath(reserve.id), { parentId: child.id }, 409);
    assert.equal(sql(`SELECT count(*) FROM pages WHERE id IN ('${reserve.id}', '${child.id}', '${other.id}') AND trash_id IS NULL`), '3');
    assert.equal(sql(`SELECT parent_id IS NULL FROM pages WHERE id = '${reserve.id}'`), 't');
    const backlinks = await call(reader, 'GET', apiPath(child.id) + '/backlinks');
    assert.equal(backlinks.items[0].id, source.id);
    const archive = await reader.request.get(docs + base + '/export');
    assert.equal(archive.status(), 200);
    console.log(width, 'trois pages masquées puis restaurées, cycle 409, backlink et export actifs');

    for (const [page, granted] of [[owner, true], [reader, false]]) {
      await page.goto(docs + pagePath(source.id));
      const opened = await followTicket(page, ticket.url);
      if (granted) await expect(opened.getByRole('dialog').getByRole('textbox', { name: 'Titre', exact: true })).toHaveValue(ticket.title);
      else await expect(opened.getByRole('heading', { name: 'Espace inaccessible', exact: true })).toBeVisible();
    }
    await call(owner, 'DELETE', base + '/members/' + readerInvite.accountId, undefined, 204);
    for (const path of [apiPath(source.id), apiPath(child.id) + '/backlinks', base + '/link-suggestions', base + '/export']) {
      await call(reader, 'GET', path, undefined, 404);
    }
    assert.deepEqual((await call(reader, 'GET', search)).items, []);
    console.log(width, 'même ticket ouvert avec les droits Circular, refusé sans eux, révocation Docs contrôlée');
  } finally {
    await Promise.all(pages.map(page => page.close()));
  }
}

try {
  await scenario(1440);
  await scenario(390);
} finally {
  await browser.close();
}
