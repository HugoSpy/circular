import { createHash } from 'node:crypto';
import { test, expect } from './fixtures';

test.use({ enableMcp: true });

test('les portées V3 et la confirmation d’archivage protègent les actions MCP', async ({ page, context, app, server }) => {
  await app.createProject('Recette mobilité', 'MOB');
  await app.createTicket({ title: 'À archiver via MCP', project: 'Recette mobilité' });
  await context.setExtraHTTPHeaders({});
  const client = page.request;
  const callback = server.url + '/mcp-callback';
  const resource = server.url + '/mcp';
  const registered = await client.post(server.url + '/register', { data: {
    redirect_uris: [callback], token_endpoint_auth_method: 'none',
    grant_types: ['authorization_code', 'refresh_token'], response_types: ['code'],
  } });
  expect(registered.status()).toBe(201);
  const { client_id } = await registered.json();
  const verifier = 'circular-v3-playwright-code-verifier-november';
  const authorization = new URL('/authorize', server.url);
  authorization.search = new URLSearchParams({
    client_id, redirect_uri: callback, resource, state: 'v3-browser',
    response_type: 'code', code_challenge_method: 'S256',
    code_challenge: createHash('sha256').update(verifier).digest('base64url'),
    scope: 'circular:read circular:tickets:read circular:tickets:write circular:projects:read circular:projects:write',
  }).toString();

  await page.goto(authorization.href);
  const heading = page.getByRole('heading', { name: 'Autoriser Client MCP dans Circular' });
  await expect(heading).toBeFocused();
  const allow = page.getByRole('button', { name: 'Autoriser les accès sélectionnés', exact: true });
  await expect(allow).toBeDisabled();
  await page.getByRole('combobox', { name: 'Espace autorisé' }).selectOption({ label: 'Espace browser-test' });
  const tickets = page.getByRole('group', { name: 'Tickets et triage', exact: true });
  await tickets.getByRole('checkbox', { name: 'Modifier', exact: true }).check();
  await expect(tickets.getByRole('checkbox', { name: 'Consulter', exact: true })).toBeChecked();
  const planning = page.getByRole('group', { name: 'Projets et feuille de route', exact: true });
  await planning.getByRole('checkbox', { name: 'Modifier', exact: true }).check();
  await allow.click();
  await page.waitForURL(url => url.pathname === '/mcp-callback' && url.searchParams.has('code'));
  const issued = await client.post(server.url + '/token', { form: {
    grant_type: 'authorization_code', client_id, redirect_uri: callback, code_verifier: verifier, resource,
    code: new URL(page.url()).searchParams.get('code')!,
  } });
  expect(issued.status()).toBe(200);
  const { access_token } = await issued.json();
  async function mcp(name: string, args: Record<string, unknown>) {
    const response = await client.post(resource, {
      headers: { Accept: 'application/json, text/event-stream', Authorization: 'Bearer ' + access_token },
      data: { jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name, arguments: args } },
    });
    expect(response.status()).toBe(200);
    const result = (await response.json()).result;
    expect(result.isError, JSON.stringify(result.content)).toBe(false);
    return result.structuredContent;
  }

  const data = await mcp('search_tickets', { query: 'À archiver via MCP' });
  const contextResult = await mcp('get_ticket_context', { reference: data.items[0].identifier });
  const ticket = contextResult.ticket;
  const approval = await mcp('prepare_ticket_archive', { ticket_id: ticket.id, expected_updated_at: ticket.updatedAt, request_key: 'browser-v3-archive-01' });
  await page.goto(approval.url);
  await expect(page.getByRole('heading', { name: 'Archiver le ticket' })).toBeFocused();
  await expect(page.getByText(ticket.identifier + ' · À archiver via MCP', { exact: true })).toBeVisible();
  const confirm = page.getByRole('button', { name: 'Confirmer', exact: true });
  await expect(confirm).toBeDisabled();
  await page.getByRole('checkbox', { name: 'Je confirme cette action sur la cible indiquée.' }).check();
  await confirm.click();
  await expect(page.getByRole('status')).toHaveText('Ticket archivé.');
  const listed = await mcp('search_tickets', { query: 'À archiver via MCP' });
  expect(listed.items).toEqual([]);

  await mcp('save_planning', { kind: 'initiative', change: { record: { title: 'Recette de la V3' } }, request_key: 'browser-v3-initiative-01' });
  await page.goto(server.url);
  await page.getByRole('button', { name: 'Projets', exact: true }).click();
  await page.getByRole('button', { name: 'Pilotage', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Recette de la V3', exact: true })).toBeVisible();
});
