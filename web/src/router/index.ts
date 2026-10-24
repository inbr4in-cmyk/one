import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { NAV, visibleNav } from './nav'
import { useAuthStore } from '@/stores/auth'
import { t } from '@/i18n'

declare module 'vue-router' {
  interface RouteMeta {
    public?: boolean
    /** i18n key for the page title */
    title?: string
    icon?: string
    perm?: string
  }
}

const StubPage = () => import('@/pages/StubPage.vue')

const moduleRoutes: RouteRecordRaw[] = NAV.map((item) => ({
  path: item.path.slice(1),
  name: item.key,
  component: item.page ?? StubPage,
  meta: { title: `nav.${item.key}`, icon: item.icon, perm: item.perm },
}))

const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: () => import('@/pages/LoginPage.vue'), meta: { public: true, title: 'login.title' } },
  { path: '/2fa', name: 'setup-2fa', component: () => import('@/pages/TwoFactorSetupPage.vue'), meta: { title: 'setup2fa.title' } },
  {
    path: '/',
    component: () => import('@/components/layout/AppShell.vue'),
    children: [
      { path: '', name: 'home', component: StubPage },
      ...moduleRoutes,
      { path: ':rest(.*)*', name: 'not-found', component: () => import('@/pages/NotFoundPage.vue'), meta: { title: 'notFound.title' } },
    ],
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: (_to, _from, saved) => saved ?? { top: 0 },
})

/** First page the user may open. Security is always allowed, so there is always one. */
export function homePath(): string {
  const auth = useAuthStore()
  return visibleNav(auth.can)[0]?.path ?? '/settings/security'
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
  if (to.name === 'setup-2fa' || to.name === 'home') return homePath()
  if (to.meta.perm && !auth.can(to.meta.perm)) return homePath()
  return true
})

router.afterEach((to) => {
  const title = to.meta.title ? t(to.meta.title) : ''
  document.title = title ? `${title} · One English` : 'One English'
})
