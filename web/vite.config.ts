import { fileURLToPath, URL } from 'node:url'
import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'

/**
 * `vite build --mode demo` (npm run build:demo): the offline demo. Boots from src/demo/entry.ts, uses
 * self-hosted fonts instead of Google Fonts and gets an explicit page background before CSS loads.
 */
function demoHtml(): Plugin {
  return {
    name: 'one-english-demo-html',
    transformIndexHtml: {
      order: 'pre',
      handler: (html) =>
        html
          .replace(/\s*<link rel="preconnect"[^>]*>/g, '')
          .replace(/\s*<link\s+rel="stylesheet"\s+href="https:\/\/fonts\.googleapis\.com[^>]*>/, '')
          .replace('/src/main.ts', '/src/demo/entry.ts')
          .replace(
            '</head>',
            '  <style>body{margin:0;background:#FAF6F3}@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) body{background:#0A1630}}:root[data-theme="dark"] body{background:#0A1630}</style>\n  </head>',
          ),
    },
  }
}

export default defineConfig(({ mode }) => ({
  plugins: mode === 'demo' ? [vue(), demoHtml()] : [vue()],
  ...(mode === 'demo' ? { base: './', build: { outDir: 'dist-demo', emptyOutDir: true } } : {}),
  define: {
    // vue-i18n feature flags: Composition API only, no devtools in production.
    __VUE_I18N_FULL_INSTALL__: true,
    __VUE_I18N_LEGACY_API__: false,
    __INTLIFY_PROD_DEVTOOLS__: false,
  },
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      // Override with API_PROXY=http://host:port npm run dev
      '/api': { target: process.env.API_PROXY ?? 'http://localhost:8000', changeOrigin: true, ws: true },
    },
  },
}))
