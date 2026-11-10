/** Sidebar / bottom-nav items. Each one is shown only when the user holds `perm`. */
export interface NavItem {
  key: string
  path: string
  icon: string
  /** `module.action` from /auth/me permissions (any of a list); omitted = every staff member */
  perm?: string | string[]
  group: 'main' | 'settings'
  /** Key in GET /api/counters; `soft` = not urgent, not red */
  counter?: 'inbox' | 'chats' | 'crm' | 'tasks'
  soft?: boolean
  /** Built page; the rest render the "in development" stub */
  page?: () => Promise<unknown>
  /** Route pattern when it differs from `path` (optional params) */
  route?: string
  /** i18n key under `nav.` when it differs from `key` */
  label?: string
}

export const NAV: NavItem[] = [
  { key: 'dashboard', path: '/dashboard', icon: 'dash', perm: 'dashboard.view', group: 'main', page: () => import('@/pages/dashboard/DashboardPage.vue') },
  { key: 'crm', path: '/crm', icon: 'crm', perm: 'crm.view', group: 'main', counter: 'crm', page: () => import('@/pages/crm/CrmPage.vue') },
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
  { key: 'finance', path: '/finance', icon: 'trend', perm: 'finance.view', group: 'main', page: () => import('@/pages/finance/FinancePage.vue') },
  { key: 'payroll', path: '/payroll', icon: 'salary', perm: 'payroll.view', group: 'main', page: () => import('@/pages/payroll/PayrollPage.vue') },
  { key: 'tasks', path: '/tasks', icon: 'task', perm: 'tasks.view', group: 'main', counter: 'tasks', soft: true, page: () => import('@/pages/tasks/TasksPage.vue') },
  { key: 'coins', path: '/coins', icon: 'coin', perm: ['coins.view', 'shop.view'], group: 'main', page: () => import('@/pages/coins/CoinsPage.vue') },
  { key: 'books', path: '/books', route: '/books/:tab(transfers|report)?', icon: 'book', perm: 'books.view', group: 'main', page: () => import('@/pages/books/BooksPage.vue') },
  { key: 'complaints', path: '/complaints', icon: 'flag', perm: 'complaints.view', group: 'main', route: '/complaints/:id(\\d+)?', page: () => import('@/pages/complaints/ComplaintsPage.vue') },
  { key: 'training', path: '/training', icon: 'learning-base', perm: 'training.view', group: 'main', page: () => import('@/pages/training/TrainingPage.vue') },
  { key: 'roles', path: '/settings/roles', icon: 'key', perm: 'roles.view', group: 'settings', page: () => import('@/pages/settings/RolesPage.vue') },
  { key: 'staff', path: '/settings/staff', icon: 'teachers', perm: 'staff.view', group: 'settings', page: () => import('@/pages/settings/StaffPage.vue') },
  { key: 'dictionaries', path: '/settings/dictionaries', icon: 'book', perm: ['settings.edit', 'finance.edit', 'branches.edit'], group: 'settings', page: () => import('@/pages/settings/DictionariesPage.vue') },
  { key: 'settingsPage', path: '/settings/general', icon: 'gear', perm: 'settings.view', group: 'settings', page: () => import('@/pages/settings/SettingsPage.vue') },
  {
    key: 'documents', path: '/settings/documents', icon: 'file', perm: ['settings.view', 'students.view'], group: 'settings',
    page: () => import('@/pages/settings/DocumentsPage.vue'),
  },
  {
    key: 'security', path: '/settings/security', icon: 'shield', group: 'settings',
    page: () => import('@/pages/SecurityPage.vue'),
  },
  { key: 'audit', path: '/settings/audit', icon: 'log', perm: 'audit.view', group: 'settings', page: () => import('@/pages/settings/AuditPage.vue') },
]

/** Detail pages: not in the menu, highlighted under their parent item. */
export const DETAIL_ROUTES: { name: string; path: string; parent?: string; perm?: string; title?: string; page: () => Promise<unknown> }[] = [
  { name: 'student', path: '/students/:id(\\d+)', parent: 'students', perm: 'students.view', page: () => import('@/pages/students/StudentPage.vue') },
  { name: 'import', path: '/students/import', parent: 'students', perm: 'students.create', page: () => import('@/pages/students/ImportPage.vue') },
  {
    name: 'old-crm-import', path: '/settings/import', parent: 'settingsPage', perm: 'import.run', title: 'oldCrm.title',
    page: () => import('@/pages/settings/OldCrmImportPage.vue'),
  },
  { name: 'group', path: '/groups/:id(\\d+)', parent: 'groups', perm: 'schedule.view', page: () => import('@/pages/groups/GroupPage.vue') },
  { name: 'lesson-attendance', path: '/attendance/:lessonId(\\d+)', parent: 'attendance', perm: 'attendance.view', page: () => import('@/pages/attendance/AttendanceSheetPage.vue') },
  { name: 'task', path: '/tasks/:id(\\d+)', parent: 'tasks', perm: 'tasks.view', page: () => import('@/pages/tasks/TaskPage.vue') },
  { name: 'course', path: '/training/:id(\\d+)', parent: 'training', perm: 'training.view', page: () => import('@/pages/training/CoursePage.vue') },
  { name: 'feedback', path: '/feedback', title: 'nav.feedback', page: () => import('@/pages/FeedbackPage.vue') },
  { name: 'rules', path: '/rules', title: 'nav.rules', page: () => import('@/pages/RulesPage.vue') },
]

export function allowed(perm: string | string[] | undefined, can: (perm: string) => boolean): boolean {
  if (!perm) return true
  return Array.isArray(perm) ? perm.some(can) : can(perm)
}

export function visibleNav(can: (perm: string) => boolean): NavItem[] {
  return NAV.filter((i) => allowed(i.perm, can))
}
