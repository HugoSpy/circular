import { createHash } from 'node:crypto';
import { test, expect } from './fixtures';

test.use({ enableMcp: true });

test('un assistant obtient séparément la lecture et l’écriture et chaque accord peut être révoqué', async ({ page, context, server, app }) => {
  await app.createProject('Application Mobile', 'MOBILE');
  await app.createTicket({ title: 'Crash au démarrage', project: 'Application Mobile' });
  const client = page.request;
  const redirectUri = server.url + '/mcp-callback';
  const resource = server.url + '/mcp';
  const registration = await client.post(server.url + '/register', { data: {
    redirect_uris: [redirectUri], token_endpoint_auth_method: 'none',
    grant_types: ['authorization_code', 'refresh_token'], response_types: ['code'],
  } });
  expect(registration.status()).toBe(201);
  const { client_id } = await registration.json();
  const verifier = 'circular-browser-pkce-verifier-with-enough-characters';
  const authorization = new URL('/authorize', server.url);
  authorization.search = new URLSearchParams({
    client_id, redirect_uri: redirectUri, resource, state: 'mcp-browser-test',
    response_type: 'code', code_challenge_method: 'S256',
    code_challenge: createHash('sha256').update(verifier).digest('base64url'),
  }).toString();

  const session = await (await client.get(server.url + '/api/auth/me')).json();
  await context.setExtraHTTPHeaders({});
  const logout = await client.post(server.url + '/api/auth/logout', {
    data: {}, headers: { 'X-CSRF-Token': session.csrfToken },
  });
  expect(logout.status()).toBe(204);
  await page.goto(authorization.href);
  await expect(page.getByRole('heading', { name: 'Connectez-vous à Circular' })).toBeVisible();
  await page.getByRole('textbox', { name: 'Pseudo ou adresse e-mail' }).fill('browser.test@epita.fr');
  await page.getByLabel('Mot de passe', { exact: true }).fill('Browser-test-passphrase-2026!');
  await page.getByRole('button', { name: 'Se connecter', exact: true }).click();
  const allow = page.getByRole('button', { name: 'Autoriser la lecture' });
  await expect(allow).toBeDisabled();
  await page.getByRole('combobox', { name: 'Espace autorisé' }).selectOption({ label: 'Espace browser-test' });
  await allow.click();
  await page.waitForURL(new RegExp('/mcp-callback\\?'));
  const callback = new URL(page.url());
  expect(callback.searchParams.get('state')).toBe('mcp-browser-test');
  const code = callback.searchParams.get('code');
  expect(code).toBeTruthy();
  const token = await client.post(server.url + '/token', { form: {
    grant_type: 'authorization_code', client_id, redirect_uri: redirectUri,
    code: code!, code_verifier: verifier, resource,
  } });
  expect(token.status()).toBe(200);
  const { access_token } = await token.json();
  const search = () => client.post(resource, {
    headers: { Authorization: `Bearer ${access_token}`, Accept: 'application/json, text/event-stream' },
    data: { jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'search_tickets', arguments: { query: 'démarrage' } } },
  });
  const result = await search();
  expect(result.status()).toBe(200);
  expect((await result.json()).result.structuredContent.items).toEqual([expect.objectContaining({ title: 'Crash au démarrage' })]);

  const writeAuthorization = new URL(authorization);
  writeAuthorization.searchParams.set('scope', 'circular:read circular:write');
  await page.goto(writeAuthorization.href);
  await expect(page.getByRole('heading', { name: 'Autoriser Client MCP à lire et à écrire dans Circular' })).toBeFocused();
  await expect(page.getByText('Créer un ticket dans un projet où vous pouvez le faire.')).toBeVisible();
  await expect(page.getByText('Ajouter un commentaire à un ticket que vous pouvez commenter.')).toBeVisible();
  const allowWrite = page.getByRole('button', { name: 'Autoriser la lecture et l’écriture', exact: true });
  await expect(allowWrite).toBeDisabled();
  await page.getByRole('button', { name: 'Refuser', exact: true }).click();
  await page.waitForURL(url => url.pathname === '/mcp-callback' && url.searchParams.get('error') === 'access_denied');
  expect((await search()).status()).toBe(200);

  await page.goto(writeAuthorization.href);
  await page.getByRole('combobox', { name: 'Espace autorisé' }).selectOption({ label: 'Espace browser-test' });
  await allowWrite.click();
  await page.waitForURL(url => url.pathname === '/mcp-callback' && url.searchParams.has('code'));
  const writeToken = await client.post(server.url + '/token', { form: {
    grant_type: 'authorization_code', client_id, redirect_uri: redirectUri,
    code: new URL(page.url()).searchParams.get('code')!, code_verifier: verifier, resource,
  } });
  expect(writeToken.status()).toBe(200);
  const { access_token: writeAccess, scope } = await writeToken.json();
  expect(scope).toBe('circular:read circular:write');
  const call = (bearer: string, name: string, args: Record<string, unknown>) => client.post(resource, {
    headers: { Authorization: `Bearer ${bearer}`, Accept: 'application/json, text/event-stream' },
    data: { jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name, arguments: args } },
  });
  const projects = await (await call(writeAccess, 'list_projects', {})).json();
  const projectId = projects.result.structuredContent.items.find((project: { name: string }) => project.name === 'Application Mobile').id;
  const args = { project_id: projectId, title: 'Ticket créé depuis MCP', request_key: 'browser-create-0001' };
  expect((await call(access_token, 'create_ticket', args)).status()).toBe(403);
  const created = (await (await call(writeAccess, 'create_ticket', args)).json()).result.structuredContent;
  const comment = await call(writeAccess, 'add_comment', { ticket_id: created.id, body: 'Compte rendu depuis MCP', request_key: 'browser-comment-001' });
  expect((await comment.json()).result.structuredContent.ticketId).toBe(created.id);
  await page.goto(created.url);
  await expect(page.getByText('Ticket créé depuis MCP', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('Compte rendu depuis MCP', { exact: true })).toBeVisible();

  await page.goto(server.url + '/?settings=integrations');
  await expect(page.getByRole('textbox', { name: 'Adresse du serveur MCP' })).toHaveValue(resource);
  const revokeWrite = page.getByRole('button', { name: 'Révoquer Client MCP pour Espace browser-test (lecture et écriture)', exact: true });
  await revokeWrite.click();
  await page.getByRole('dialog', { name: 'Révoquer l’accès de Client MCP en lecture et écriture ?' })
    .getByRole('button', { name: 'Révoquer l’accès' }).click();
  await expect(page.getByRole('heading', { name: 'Assistants IA' })).toBeFocused();
  await expect(page.getByText('Espace browser-test · Lecture seule', { exact: true })).toBeVisible();
  expect((await call(writeAccess, 'create_ticket', args)).status()).toBe(401);
  expect((await search()).status()).toBe(200);
  const revoke = page.getByRole('button', { name: 'Révoquer Client MCP pour Espace browser-test (lecture seule)', exact: true });
  await revoke.click();
  const dialog = page.getByRole('dialog', { name: 'Révoquer l’accès de Client MCP en lecture seule ?' });
  await dialog.getByRole('button', { name: 'Annuler' }).click();
  await expect(revoke).toBeFocused();
  await revoke.click();
  await dialog.getByRole('button', { name: 'Révoquer l’accès' }).click();
  await expect(page.getByText('Aucune connexion autorisée.')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Assistants IA' })).toBeFocused();
  expect((await search()).status()).toBe(401);
});
