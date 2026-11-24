import { createHash } from 'node:crypto';
import { test, expect } from './fixtures';

test.use({ enableMcp: true });

test('un assistant reçoit un accès en lecture dans un espace puis le perd à la révocation', async ({ page, context, server, app }) => {
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

  await page.goto(server.url + '/?settings=integrations');
  await expect(page.getByRole('textbox', { name: 'Adresse du serveur MCP' })).toHaveValue(resource);
  const revoke = page.getByRole('button', { name: 'Révoquer Client MCP pour Espace browser-test' });
  await revoke.click();
  const dialog = page.getByRole('dialog', { name: 'Révoquer l’accès de Client MCP ?' });
  await dialog.getByRole('button', { name: 'Annuler' }).click();
  await expect(revoke).toBeFocused();
  await revoke.click();
  await dialog.getByRole('button', { name: 'Révoquer l’accès' }).click();
  await expect(page.getByText('Aucune connexion autorisée.')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Assistants IA' })).toBeFocused();
  expect((await search()).status()).toBe(401);
});
