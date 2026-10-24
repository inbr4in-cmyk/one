/** Sidebar / bottom-nav items. Each one is shown only when the user holds `perm`. */
export interface NavItem {
  key: string
  path: string
  icon: string
  /** `module.action` from /auth/me permissions; omitted = everyone signed in */
  perm?: string
  group: 'main' | 'settings'
  /** Counter key in the counters store; `soft` = not urgent, not red */
  counter?: string
  soft?: boolean
  /** Built page; the rest render the "in development" stub */
  page?: () => Promise<unknown>
}

export const NAV: NavItem[] = [
  { key: 'dashboard', path: '/dashboard', icon: 'dash', perm: 'dashboard.view', group: 'main' },
  { key: 'crm', path: '/crm', icon: 'crm', perm: 'crm.view', group: 'main', counter: 'crm' },
  { key: 'inbox', path: '/inbox', icon: 'inbox', perm: 'inbox.view', group: 'main', counter: 'inbox' },
  { key: 'chats', path: '/chats', icon: 'chat', perm: 'chats.use', group: 'main', counter: 'chats', soft: true },
  { key: 'schedule', path: '/schedule', icon: 'cal', perm: 'schedule.view', group: 'main' },
  { key: 'students', path: '/students', icon: 'users', perm: 'students.view', group: 'main' },
  { key: 'attendance', path: '/attendance', icon: 'check', perm: 'attendance.view', group: 'main' },
  { key: 'finance', path: '/finance', icon: 'wallet', perm: 'finance.view', group: 'main' },
  { key: 'coins', path: '/coins', icon: 'coin', perm: 'coins.view', group: 'main' },
  { key: 'tasks', path: '/tasks', icon: 'task', perm: 'tasks.view', group: 'main', counter: 'tasks', soft: true },
  { key: 'books', path: '/books', icon: 'book', perm: 'books.view', group: 'main' },
  { key: 'roles', path: '/settings/roles', icon: 'key', perm: 'roles.view', group: 'settings' },
  {
    key: 'security', path: '/settings/security', icon: 'shield', group: 'settings',
    page: () => import('@/pages/SecurityPage.vue'),
  },
  { key: 'audit', path: '/settings/audit', icon: 'log', perm: 'audit.view', group: 'settings' },
]

export function visibleNav(can: (perm: string) => boolean): NavItem[] {
  return NAV.filter((i) => !i.perm || can(i.perm))
}
