import { createRouter, createWebHashHistory, createWebHistory, type RouteMeta, type RouteRecordRaw } from 'vue-router'
import { allowed, DETAIL_ROUTES, NAV, visibleNav } from './nav'
import { useAuthStore } from '@/stores/auth'
import { t } from '@/i18n'

declare module 'vue-router' {
  interface RouteMeta {
    public?: boolean
    /** i18n key for the page title */
    title?: string
    icon?: string
    perm?: string | string[]
    /** Student / parent cabinet route */
    portal?: boolean
    /** Nav item highlighted for a detail page */
    parent?: string
    /** Full-height page without bottom padding (inbox, chats) */
    flush?: boolean
  }
}

const StubPage = () => import('@/pages/StubPage.vue')

const moduleRoutes: RouteRecordRaw[] = NAV.map((item) => ({
  path: (item.route ?? item.path).slice(1),
  name: item.key,
  component: item.page ?? StubPage,
  meta: { title: `nav.${item.key}`, icon: item.icon, perm: item.perm, flush: item.key === 'inbox' || item.key === 'chats' },
}))

const detailRoutes: RouteRecordRaw[] = DETAIL_ROUTES.map((d) => ({
  path: d.path.slice(1),
  name: d.name,
  component: d.page,
  meta: { title: d.title ?? `nav.${d.parent}`, perm: d.perm, parent: d.parent },
}))

const portal = (path: string, name: string, title: string, page: () => Promise<unknown>, extra: RouteMeta = {}): RouteRecordRaw =>
  ({ path, name, component: page, meta: { portal: true, title, ...extra } })

const portalRoutes: RouteRecordRaw[] = [
  portal('', 'portal-home', 'portal.nav.home', () => import('@/pages/portal/PortalHome.vue')),
  portal('schedule', 'portal-schedule', 'portal.nav.schedule', () => import('@/pages/portal/PortalSchedule.vue')),
  portal('homework', 'portal-homework', 'portal.nav.homework', () => import('@/pages/portal/PortalHomework.vue')),
  portal('progress', 'portal-progress', 'portal.nav.progress', () => import('@/pages/portal/PortalProgress.vue')),
  portal('payments', 'portal-payments', 'portal.nav.payments', () => import('@/pages/portal/PortalPayments.vue')),
  portal('coins', 'portal-coins', 'portal.nav.coins', () => import('@/pages/portal/PortalCoins.vue')),
  { path: 'shop', redirect: '/portal/coins' },
  { path: 'children/:id(\\d+)', redirect: (to) => ({ path: '/portal', query: { child: String(to.params.id) } }) },
  portal('chats/:id(\\d+)?', 'portal-chats', 'portal.nav.chats', () => import('@/pages/chats/ChatsPage.vue'), { flush: true }),
  portal('feedback', 'portal-feedback', 'nav.feedback', () => import('@/pages/FeedbackPage.vue')),
  portal('rules', 'portal-rules', 'nav.rules', () => import('@/pages/RulesPage.vue')),
  portal('profile', 'portal-profile', 'portal.nav.profile', () => import('@/pages/portal/PortalProfile.vue')),
]

const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: () => import('@/pages/LoginPage.vue'), meta: { public: true, title: 'login.title' } },
  { path: '/2fa', name: 'setup-2fa', component: () => import('@/pages/TwoFactorSetupPage.vue'), meta: { title: 'setup2fa.title' } },
  { path: '/portal', component: () => import('@/components/portal/PortalShell.vue'), children: portalRoutes },
  {
    path: '/',
    component: () => import('@/components/layout/AppShell.vue'),
    children: [
      { path: '', name: 'home', component: StubPage },
      ...moduleRoutes,
      ...detailRoutes,
      // Links the server puts into notifications
      { path: 'payroll/my', redirect: { path: '/payroll', query: { tab: 'my' } } },
      { path: 'shop/orders', redirect: '/coins' },
      { path: 'crm/leads/:id(\\d+)', redirect: (to) => ({ path: '/crm', query: { lead: String(to.params.id) } }) },
      { path: 'lessons/:id(\\d+)', redirect: (to) => `/attendance/${String(to.params.id)}` },
      { path: ':rest(.*)*', name: 'not-found', component: () => import('@/pages/NotFoundPage.vue'), meta: { title: 'notFound.title' } },
    ],
  },
]

export const router = createRouter({
  // The offline demo is a static page that can sit under any path, so it routes by hash.
  history: import.meta.env.VITE_DEMO === '1' ? createWebHashHistory() : createWebHistory(),
  routes,
  scrollBehavior: (_to, _from, saved) => saved ?? { top: 0 },
})

/** First page the user may open. Security is always allowed, so there is always one. */
export function homePath(): string {
  const auth = useAuthStore()
  if (auth.user && !auth.isStaff) return '/portal'
  return visibleNav(auth.can)[0]?.path ?? '/settings/security'
}

/** Notification links written for staff screens, mapped onto the cabinet. */
function portalPath(path: string): string {
  const chat = /^\/chats\/(\d+)/.exec(path)
  if (chat) return `/portal/chats/${chat[1]}`
  if (path.startsWith('/complaints') || path.startsWith('/feedback')) return '/portal/feedback'
  if (path.startsWith('/rules')) return '/portal/rules'
  return '/portal'
}

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.init()

  if (to.meta.public) {
    return auth.isAuthenticated && to.name === 'login' ? homePath() : true
  }
  if (!auth.isAuthenticated) {
    return { name: 'login', query: to.fullPath !== '/' ? { redirect: to.fullPath } : {} }
  }
  if (auth.mfaSetupRequired) return to.name === 'setup-2fa' ? true : { name: 'setup-2fa' }
  // Students and parents live in their cabinet; staff never act through it.
  if (!auth.isStaff) return to.meta.portal ? true : portalPath(to.path)
  if (to.meta.portal) return homePath()
  if (to.name === 'setup-2fa' || to.name === 'home') return homePath()
  if (to.name === 'complaints' && to.params.id && !auth.can('complaints.view')) return '/feedback'
  if (!allowed(to.meta.perm, auth.can)) return homePath()
  return true
})

router.afterEach((to) => {
  const title = to.meta.title ? t(to.meta.title) : ''
  document.title = title ? `${title} · One English` : 'One English'
})
