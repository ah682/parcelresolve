import { spawn, spawnSync } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import path from 'node:path';

const args = process.argv.slice(2);
if (!args.includes('--browser-only')) {
  const result = spawnSync('make', ['verify', ...args], { stdio: 'inherit' });
  process.exit(result.status ?? 1);
}
const built = spawnSync(process.execPath, ['frontend/scripts/build.mjs'], { stdio: 'inherit' });
if (built.status !== 0) process.exit(built.status ?? 1);
const socket = createServer();
await new Promise((resolve, reject) => { socket.once('error', reject); socket.listen(0, '127.0.0.1', resolve); });
const port = socket.address().port;
await new Promise(resolve => socket.close(resolve));
const directory = await mkdtemp(path.join(tmpdir(), 'parcelresolve-browser-'));
const stamp = new Date().toISOString().replaceAll(':', '').replaceAll('.', '');
const output = process.env.PARCELRESOLVE_BROWSER_OUTPUT ?? `frontend/qa/${stamp}`;
const baseURL = `http://127.0.0.1:${port}`;
const environment = { ...process.env, PARCELRESOLVE_MODE: 'simulator', PARCELRESOLVE_DATA_DIR: directory, PARCELRESOLVE_INTAKE_MODE: 'deterministic', PARCELRESOLVE_OPERATOR_TOKEN: 'demo-operator', PARCELRESOLVE_VIEWER_TOKEN: 'demo-viewer' };
const server = spawn('.venv/bin/python', ['-m', 'uvicorn', 'parcelresolve.api:create_app', '--factory', '--host', '127.0.0.1', '--port', String(port), '--log-level', 'warning'], { env: environment, stdio: 'inherit' });
let spawnError;
server.once('error', error => { spawnError = error; });
let code = 1;
try {
  const deadline = Date.now() + 30000;
  while (true) {
    if (spawnError) throw spawnError;
    if (server.exitCode !== null) throw new Error(`Isolated demo exited before readiness: ${server.exitCode}`);
    try { const response = await fetch(`${baseURL}/api/meta`, { headers: { Authorization: 'Bearer demo-operator' }, signal: AbortSignal.timeout(1000) }); if (response.ok) break; } catch { /* Start-up probe; no mutation. */ }
    if (Date.now() > deadline) throw new Error('Isolated local demo did not become ready in 30 seconds.');
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  console.log(`Browser QA uses a fresh disposable simulator at ${baseURL}. Evidence: ${output}`);
  const result = spawnSync(process.execPath, ['frontend/scripts/browser-check.mjs'], { env: { ...environment, PARCELRESOLVE_BROWSER_URL: baseURL, PARCELRESOLVE_BROWSER_OUTPUT: output }, stdio: 'inherit' });
  code = result.status ?? 1;
} finally {
  server.kill('SIGTERM');
  await new Promise(resolve => { const timer = setTimeout(() => { server.kill('SIGKILL'); resolve(); }, 5000); server.once('exit', () => { clearTimeout(timer); resolve(); }); if (server.exitCode !== null) { clearTimeout(timer); resolve(); } });
  await rm(directory, { recursive: true, force: true });
}
process.exitCode = code;
