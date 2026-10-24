# One English — web

The staff CRM and the student/parent cabinet in one Vue 3 app. Staff sign in with phone + password (+ 2FA). Students and parents sign in with a WhatsApp code and land in `/portal`, a mobile-first layout that the Flutter app mirrors.

Stack: Vue 3.5 (`<script setup>`, TypeScript strict), vue-router, Pinia, vue-i18n (ru, kk), Vite. No UI framework: components live in `src/components/ui`, design tokens in `src/styles/tokens.css`.

## Run

Needs Node 20+ and the API running (see the root `README.md` for the backend and the demo seed).

```bash
cd web
npm install
npm run dev                                   # http://localhost:5173, proxies /api (HTTP + WebSocket) to :8000
API_PROXY=http://localhost:8010 npm run dev   # API on another port
npx vite --port 5174 --strictPort             # dev server on another port
```

With the demo seed (`python -m app.seed --demo`):

| Who | Login |
|---|---|
| Owner | `+7 701 000 00 01` / `Demo-pass-2026` |
| Branch admin, office manager, sales, SMM, teachers | `+7 705 900 00 01` … `10`, same password (the seed prints who is who) |
| Students / parents | "Ученик или родитель" tab, phone from the seed; the code comes over WhatsApp (in dev without Meta tokens it is only logged by the API) |

Run the API with `OE_REQUIRE_STAFF_2FA=false` locally, or staff are sent through 2FA setup first.

## Build

```bash
npm run typecheck   # vue-tsc, no emit
npm run build       # vue-tsc -b && vite build → dist/
npm run preview     # serve dist/ locally
```

`npm run build` must pass before anything is merged.

## Environment

The web app has no build-time secrets and reads no `VITE_*` variables. It expects to be served from the **same origin** as the API:

- requests go to `/api/...`, the refresh token is an httpOnly cookie, the access token lives in memory only;
- every request carries `X-Requested-With: one-english` (CSRF guard on the API);
- realtime uses one WebSocket per tab at `/api/ws?ticket=…` (ticket from `POST /api/ws/ticket`).

| Variable | Where | Meaning |
|---|---|---|
| `API_PROXY` | `npm run dev` only | API origin for the dev proxy, default `http://localhost:8000` |

In production serve `dist/` as static files with an SPA fallback and proxy `/api` (including the WebSocket upgrade) to the API, for example with nginx:

```nginx
location /api/ { proxy_pass http://api:8000; proxy_http_version 1.1;
                 proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade";
                 proxy_set_header Host $host; proxy_set_header X-Forwarded-For $remote_addr; }
location /     { root /srv/web/dist; try_files $uri /index.html; }
location /assets/ { root /srv/web/dist; expires 1y; add_header Cache-Control "public, immutable"; }
```

Set `OE_CORS_ORIGINS` on the API only if the web app is served from a different origin.

## Structure

```
src/
  main.ts, App.vue      bootstrap: Pinia, router, i18n, theme, icon sprite
  api/                  one module per backend area (typed requests); http.ts = fetch wrapper, refresh-on-401, errors
  stores/               Pinia: auth (user, permissions, can()), branch filter, refs (branches/levels/staff), counters,
                        portal (children, selected child), toast
  router/
    nav.ts              sidebar items: path, icon, permission, counter, page; the single place to add a staff screen
    index.ts            routes, auth/2FA/rules guards, portal routes, redirects for links sent in notifications
  pages/                one folder per area (dashboard, crm, inbox, chats, schedule, groups, students, attendance,
                        payments, finance, payroll, tasks, books, coins, complaints, training, settings, portal)
  components/
    ui/                 primitives: UiButton, UiInput, UiSelect, UiModal/UiDrawer/UiPrompt, UiTabs, UiSegmented,
                        UiPeriod, UiTable, UiChip, UiEmptyState, UiSkeleton, UiToastHost, IconSprite …
    layout/             AppShell (sidebar, top bar, bottom nav on phones), search, notifications, check-in widget
    portal/             PortalShell (child switcher, bottom tabs, blocked banner)
    <area>/             components shared within an area (crm, chat, students, store, homework, compliance …)
  composables/          useDialog (focus trap, Esc), useRealtime (WebSocket), useHotkey, useMediaQuery …
  i18n/                 ru.ts + kk.ts (shell), modules.*.ts (batch 2 screens), ops.*.ts (batch 3–4 screens);
                        kk files are typed against the ru shape, so a missing key fails the build
  styles/               tokens.css (colors, radii, motion, light + dark), base, components, shell, motion,
                        modules.css / ops.css / portal.css (screen styles), auth.css
  utils/                dates, money and period formatting, phone, safe URLs, icons, storage
  assets/sprite.svg     icon sprite (<UiIcon name="…">)
```

## Conventions

- **Design**: the reference is `docs/design/web.html`. Never hardcode colors: use the tokens in `tokens.css`, which define light and dark (`prefers-color-scheme` plus a manual `data-theme`). Navy is primary; red is only for the main CTA, unread and urgent. Unbounded for headings and numbers, Golos for UI.
- **Motion**: 120–280 ms, ease-out, transform/opacity only; `motion.css` turns it off under `prefers-reduced-motion`.
- **Text**: every string goes through i18n in both ru and kk. A literal `{` starts interpolation in vue-i18n; dynamic keys (`t(\`x.${k}\`)`) must exist in both languages or be guarded with `te()`.
- **Permissions**: `auth.can('module.action', scope?)` with scopes own < branch < network. Hide what the user cannot do; the API enforces everything again, the UI is never the security boundary.
- **Phones first**: every screen works at 360 px with no horizontal page scroll (wide tables scroll inside `.scroll-x`). The portal is designed for phones and widens to a tab row from 900 px.
- **Links from the server** (notifications, files) go through `utils/url.ts` `safeUrl()` before they reach `href`.
- **Local storage** only for per-device conveniences (theme, language, selected child, unsent drafts), always wrapped in try/catch (`utils/storage.ts`).

## Adding a staff screen

1. Add the API calls and types in `src/api/<area>.ts`.
2. Create `src/pages/<area>/<Name>Page.vue`.
3. Add an entry in `src/router/nav.ts` with `perm` and `page`, and the label under `nav.<key>` in `ru.ts` and `kk.ts`.
4. Add its strings to the ru and kk files, check light/dark and 360 px, run `npm run build`.
