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
            '  <style>body{margin:0;background:#FAF6F3}@media (prefers-color-scheme:dark){:root:not([data-theme]) body{background:#0A1630}}' +
              ':root[data-theme="dark"] body{background:#0A1630}:root[data-theme="ocean"] body{background:#F2F7F7}' +
              ':root[data-theme="graphite"] body{background:#15171B}:root[data-theme="sand"] body{background:#F6F0E6}</style>\n  </head>',
          ),
    },
  }
}

/** Every build gets an id: it is baked into the bundle and written to /version.json, so an open tab can see that a newer build is on the server. */
const BUILD_ID = Date.now().toString(36)
function buildVersion(): Plugin {
  return {
    name: 'one-english-build-version',
    generateBundle() {
      this.emitFile({ type: 'asset', fileName: 'version.json', source: JSON.stringify({ build: BUILD_ID }) })
    },
  }
}

export default defineConfig(({ mode }) => ({
  plugins: mode === 'demo' ? [vue(), demoHtml()] : [vue(), buildVersion()],
  // Older phones (iOS 13+, Android WebView 80+) must open the public links too: forms, tests, lesson rating.
  ...(mode === 'demo' ? { base: './', build: { outDir: 'dist-demo', emptyOutDir: true } } : { build: { target: ['es2019', 'chrome80', 'safari13', 'firefox78'] } }),
  define: {
    __BUILD_ID__: JSON.stringify(BUILD_ID),
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
