import { spawn } from 'node:child_process';
import { python, root, requirePython } from './python-path.mjs';
requirePython();
const children = [
  spawn(python, ['-m', 'backend'], { cwd: root, stdio: 'inherit', windowsHide: true, env: { ...process.env, PYTHONUTF8: '1' } }),
  spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1'], { cwd: root, stdio: 'inherit', windowsHide: true }),
];
let stopping = false;
function stop(code = 0) { if (stopping) return; stopping = true; process.exitCode = code; children.forEach(child => child.kill()); }
for (const child of children) {
  child.on('error', error => { console.error(error.message); stop(1); });
  child.on('exit', code => stop(code ?? 0));
}
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => stop());
