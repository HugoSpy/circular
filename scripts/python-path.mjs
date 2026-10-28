import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
export const root = fileURLToPath(new URL('../', import.meta.url));
export const python = fileURLToPath(new URL(process.platform === 'win32' ? '../.venv/Scripts/python.exe' : '../.venv/bin/python', import.meta.url));
export function requirePython() {
  if (!existsSync(python)) {
    console.error('Environnement Python absent. Créez .venv puis installez requirements-dev.txt (voir README).');
    process.exit(1);
  }
}
