/** Demo build only: roles shown on the login screen and the moment the fixtures were recorded. */

/** A Wednesday afternoon in Shymkent (UTC+5): lessons are running, the day's data is in. */
export const DEMO_NOW = '2026-10-28T11:30:00Z'

export type DemoRole = 'owner' | 'admin' | 'manager' | 'teacher'

export const DEMO_ROLES: { role: DemoRole; label: string; who: string }[] = [
  { role: 'owner', label: 'Войти как владелец', who: 'Вся сеть: финансы, зарплаты, настройки' },
  { role: 'admin', label: 'Войти как администратор', who: 'Асем Кенжебаева, филиал Янги шахар' },
  { role: 'manager', label: 'Войти как менеджер', who: 'Динара Сапарова, офис-менеджер' },
  { role: 'teacher', label: 'Войти как преподаватель', who: 'Дана Темирова, учитель' },
]

/** The demo seed's phones, so typing a real demo login also picks the right role. */
export const DEMO_PHONES: Record<string, DemoRole> = {
  '+77010000001': 'owner',
  '+77059000001': 'admin',
  '+77059000003': 'manager',
  '+77059000007': 'teacher',
}

export const DEMO_NOTICE = 'Демо-версия: изменения не сохраняются'
