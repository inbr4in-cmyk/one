/** Sidebar / bottom-nav items. Each one is shown only when the user holds `perm`. */
export interface NavItem {
  key: string
  path: string
  icon: string
  /** `module.action` from /auth/me permissions; omitted = everyone signed in */
  perm?: string
  group: 'main' | 'settings'
  /** Key in GET /api/counters; `soft` = not urgent, not red */
  counter?: 'inbox' | 'chats'
  soft?: boolean
  /** Built page; the rest render the "in development" stub */
  page?: () => Promise<unknown>
  /** Route pattern when it differs from `path` (optional params) */
  route?: string
}

export const NAV: NavItem[] = [
  { key: 'dashboard', path: '/dashboard', icon: 'dash', perm: 'dashboard.view', group: 'main' },
  { key: 'crm', path: '/crm', icon: 'crm', perm: 'crm.view', group: 'main', page: () => import('@/pages/crm/CrmPage.vue') },
  {
    key: 'inbox', path: '/inbox', route: '/inbox/:id(\\d+)?', icon: 'inbox', perm: 'inbox.view', group: 'main', counter: 'inbox',
    page: () => import('@/pages/inbox/InboxPage.vue'),
  },
  {
    key: 'chats', path: '/chats', route: '/chats/:id(\\d+)?', icon: 'chat', perm: 'chats.use', group: 'main', counter: 'chats', soft: true,
    page: () => import('@/pages/chats/ChatsPage.vue'),
  },
  { key: 'schedule', path: '/schedule', icon: 'cal', perm: 'schedule.view', group: 'main', page: () => import('@/pages/schedule/SchedulePage.vue') },
  { key: 'groups', path: '/groups', icon: 'groups', perm: 'schedule.view', group: 'main', page: () => import('@/pages/groups/GroupsPage.vue') },
  { key: 'students', path: '/students', icon: 'users', perm: 'students.view', group: 'main', page: () => import('@/pages/students/StudentsPage.vue') },
  {
    key: 'attendance', path: '/attendance', icon: 'check', perm: 'attendance.view', group: 'main',
    page: () => import('@/pages/attendance/AttendancePage.vue'),
  },
  { key: 'payments', path: '/payments', icon: 'wallet', perm: 'payments.view', group: 'main', page: () => import('@/pages/payments/PaymentsPage.vue') },
  { key: 'finance', path: '/finance', icon: 'trend', perm: 'finance.view', group: 'main' },
  { key: 'coins', path: '/coins', icon: 'coin', perm: 'coins.view', group: 'main' },
  { key: 'tasks', path: '/tasks', icon: 'task', perm: 'tasks.view', group: 'main' },
  { key: 'books', path: '/books', icon: 'book', perm: 'books.view', group: 'main' },
  { key: 'roles', path: '/settings/roles', icon: 'key', perm: 'roles.view', group: 'settings' },
  {
    key: 'security', path: '/settings/security', icon: 'shield', group: 'settings',
    page: () => import('@/pages/SecurityPage.vue'),
  },
  { key: 'audit', path: '/settings/audit', icon: 'log', perm: 'audit.view', group: 'settings' },
]

/** Detail pages: not in the menu, highlighted under their parent item. */
export const DETAIL_ROUTES = [
  { name: 'student', path: '/students/:id(\\d+)', parent: 'students', perm: 'students.view', page: () => import('@/pages/students/StudentPage.vue') },
  { name: 'group', path: '/groups/:id(\\d+)', parent: 'groups', perm: 'schedule.view', page: () => import('@/pages/groups/GroupPage.vue') },
  { name: 'lesson-attendance', path: '/attendance/:lessonId(\\d+)', parent: 'attendance', perm: 'attendance.view', page: () => import('@/pages/attendance/AttendanceSheetPage.vue') },
]

export function visibleNav(can: (perm: string) => boolean): NavItem[] {
  return NAV.filter((i) => !i.perm || can(i.perm))
}
