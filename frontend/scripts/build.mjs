import { build } from 'esbuild';
import { mkdir, copyFile, rm } from 'node:fs/promises';

await rm('frontend/dist', { recursive: true, force: true });
await mkdir('frontend/dist/assets', { recursive: true });
await build({
  entryPoints: ['frontend/src/app.ts'],
  bundle: true,
  minify: true,
  target: 'es2022',
  sourcemap: true,
  outfile: 'frontend/dist/assets/app.js',
  logLevel: 'info',
});
await copyFile('frontend/index.html', 'frontend/dist/index.html');
await build({
  entryPoints: ['frontend/src/styles.css'],
  bundle: true,
  minify: true,
  target: 'es2022',
  sourcemap: true,
  outfile: 'frontend/dist/assets/styles.css',
  logLevel: 'info',
});
