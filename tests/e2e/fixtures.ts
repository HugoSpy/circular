import { test as base, expect } from '@playwright/test';
import { spawn, type ChildProcess } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdir, mkdtemp, rm } from 'node:fs/promises';
import { createServer } from 'node:net';
import path from 'node:path';
import { setTimeout as pause } from 'node:timers/promises';
import { python, root } from '../../scripts/python-path.mjs';
import { CircularPage } from './pages/circular-page';
import { createEmptyWorkspace } from './workspace-setup';

async function freePort(): Promise<number> {
  const socket = createServer();
  await new Promise<void>((resolve, reject) => {
    socket.once('error', reject);
    socket.listen(0, '127.0.0.1', resolve);
  });
  const address = socket.address();
  if (!address || typeof address === 'string') throw new Error('Port local indisponible.');
  const port = address.port;
  await new Promise<void>((resolve, reject) => socket.close(error => error ? reject(error) : resolve()));
  return port;
}

export class LocalServer {
  readonly url: string;
  private process?: ChildProcess;
  private output = '';
  constructor(readonly database: string, readonly port: number) {
    this.url = `http://127.0.0.1:${port}`;
  }
  get logs() { return this.output; }
  async start() {
    if (!existsSync(python)) throw new Error('Créez .venv et installez requirements-dev.txt avant les tests.');
    if (!existsSync(path.join(root, 'dist', 'index.html'))) throw new Error('Exécutez npm run build avant les tests navigateur.');
    let launchError: Error | undefined;
    // Every browser test owns its SQLite file and configuration. In particular,
    // a deployment DSN/secret file from the parent shell must never redirect it.
    const environment = { ...process.env };
    for (const key of Object.keys(environment)) if (key.startsWith('CIRCULAR_')) delete environment[key];
    const child = spawn(python, ['-m', 'backend'], {
      cwd: root,
      env: { ...environment, CIRCULAR_ENV: 'test', CIRCULAR_HOST: '127.0.0.1', CIRCULAR_DB: this.database, CIRCULAR_PORT: String(this.port), PYTHONUNBUFFERED: '1' },
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    this.process = child;
    child.on('error', error => { launchError = error; });
    const record = (data: Buffer) => { this.output = (this.output + data.toString()).slice(-100_000); };
    child.stdout?.on('data', record);
    child.stderr?.on('data', record);
    const deadline = Date.now() + 15_000;
    while (Date.now() < deadline) {
      if (launchError) throw launchError;
      if (child.exitCode !== null) throw new Error(`Backend arrêté (${child.exitCode}) :\n${this.output}`);
      try {
        const response = await fetch(`${this.url}/api/health`, { signal: AbortSignal.timeout(500) });
        if (response.ok) return;
      } catch { /* Wait for the loopback server to bind; no browser timing assumptions. */ }
      await pause(100);
    }
    throw new Error(`Backend indisponible après 15 secondes :\n${this.output}`);
  }
  async stop() {
    const child = this.process;
    this.process = undefined;
    if (!child || child.exitCode !== null || child.signalCode !== null) return;
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => {
        child.kill('SIGKILL');
        reject(new Error('Le backend ne s’est pas arrêté dans les 5 secondes.'));
      }, 5_000);
      child.once('exit', () => { clearTimeout(timer); resolve(); });
      child.kill('SIGTERM');
    });
  }
  async restart() {
    await this.stop();
    await this.start();
  }
}

type Fixtures = { server: LocalServer; app: CircularPage; networkAudit: void };

export const test = base.extend<Fixtures>({
  server: async ({}, use, testInfo) => {
    const dataRoot = path.resolve(root, '.test-data');
    await mkdir(dataRoot, { recursive: true });
    const directory = await mkdtemp(path.join(dataRoot, 'browser-'));
    const server = new LocalServer(path.join(directory, 'circular.sqlite'), await freePort());
    try {
      await server.start();
      await use(server);
    } finally {
      await server.stop();
      if (testInfo.status !== testInfo.expectedStatus) {
        await testInfo.attach('backend.log', { body: server.logs, contentType: 'text/plain' });
      }
      // Only this fixture's mkdtemp directory, verified below the designated test root.
      if (path.dirname(path.resolve(directory)) !== dataRoot) throw new Error('Dossier temporaire hors de .test-data.');
      await rm(directory, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
    }
  },
  networkAudit: [async ({ context }, use) => {
    const externalRequests: string[] = [];
    const pageErrors: string[] = [];
    context.on('page', page => page.on('pageerror', error => pageErrors.push(error.message)));
    await context.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (/^https?:$/.test(url.protocol) && !['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname)) {
        externalRequests.push(`${route.request().method()} ${url.origin}`);
        await route.abort('blockedbyclient');
      } else await route.continue();
    });
    await use();
    expect(externalRequests, 'Aucun appel HTTP vers Linear ou un autre service externe').toEqual([]);
    expect(pageErrors, 'Aucune exception JavaScript dans les parcours').toEqual([]);
  }, { auto: true }],
  app: async ({ page, context, server }, use) => {
    // Existing workspace journeys start as a real authenticated user. Auth and
    // sharing journeys intentionally use page/server directly and register in UI.
    const registered = await page.request.post(`${server.url}/api/auth/register`, { data: {
      username: 'Utilisateur de test', email: 'browser.test@epita.fr', password: 'Browser-test-passphrase-2026!',
    } });
    expect(registered.status()).toBe(201);
    const workspace = await createEmptyWorkspace(page, server.url, 'browser-test');
    // The context's API request client shares the session cookie and these headers;
    // direct API setup in existing tests uses the same CSRF checks as the browser.
    await context.setExtraHTTPHeaders(workspace.headers);
    const app = new CircularPage(page);
    await page.goto(server.url);
    await expect(page.getByRole('button', { name: 'Mon compte', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Nouveau ticket', exact: true })).toBeEnabled();
    await use(app);
  },
});

export { expect } from '@playwright/test';
