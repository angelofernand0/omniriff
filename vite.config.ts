import { defineConfig } from 'vite';
import { readdirSync, readFileSync } from 'node:fs';
import { resolve, relative } from 'node:path';

const dashboard = resolve('dashboard');

// The Python server continues serving the original HTML and classic scripts.
// Only this browser build replaces app's bootstrap; the renderer is shared.
export default defineConfig({
  root: dashboard,
  publicDir: false,
  server: { host: '127.0.0.1' },
  build: { outDir: '../dist', emptyOutDir: true, target: 'es2022' },
  plugins: [{
    name: 'omniriff-browser-entry',
    transformIndexHtml: {
      order: 'pre',
      handler(html) {
        return html.replace(/<script src="(?:brand|app|juice|riff|coach|stage|tape|manual)\.js"><\/script>/g, '')
          .replace('<script>OmniBrand.mount();</script>', '<script type="module" src="/browser/entry.ts"></script>');
      },
    },
    generateBundle() {
      const emit = (path: string) => this.emitFile({ type: 'asset', fileName: relative(dashboard, path).replaceAll('\\', '/'), source: readFileSync(path) });
      for (const entry of readdirSync(dashboard, { withFileTypes: true })) {
        if (entry.isFile() && entry.name.endsWith('.js')) emit(resolve(dashboard, entry.name));
      }
      const walk = (dir: string) => {
        for (const entry of readdirSync(dir, { withFileTypes: true })) {
          const path = resolve(dir, entry.name);
          if (entry.isDirectory()) walk(path); else emit(path);
        }
      };
      walk(resolve(dashboard, 'brand'));
    },
  }],
});
