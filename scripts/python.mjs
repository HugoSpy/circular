import { spawn } from 'node:child_process';
import { python, root, requirePython } from './python-path.mjs';
requirePython();
const child = spawn(python, process.argv.slice(2), { cwd: root, stdio: 'inherit', windowsHide: true, env: { ...process.env, PYTHONUTF8: '1' } });
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal));
child.on('error', error => { console.error(error.message); process.exitCode = 1; });
child.on('exit', code => { process.exitCode = code ?? 0; });
