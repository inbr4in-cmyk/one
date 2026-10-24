import { http, qs } from './http'

export interface PortalChild {
  id: number
  full_name: string
  photo_url: string | null
  status: string
  branch: { id: number; name: string; phone: string | null; address: string | null }
  level: string | null
  lessons_left: number
  money_balance: number
  debt: boolean
  /** Access paused for non-payment: only payments stay open */
  blocked: boolean
  stars: number
  coins: number
  groups: { id: number; name: string; level: string | null; teacher: string | null; teacher_id: number; chat_id: number | null }[]
}

export interface PortalMe {
  kind: 'student' | 'parent'
  full_name: string
  children: PortalChild[]
}

export interface PortalLesson {
  id: number
  starts_at: string
  ends_at: string
  group: string | null
  room: string | null
  teacher: string | null
  status: 'planned' | 'done' | 'cancelled'
  cancel_reason: string | null
  topic: string | null
}

export interface PortalMark {
  lesson_id: number
  at: string
  group: string | null
  status: 'present' | 'absent' | 'late' | 'excused'
  grade: number | null
  comment: string | null
  stars: number | null
  charged: boolean
  my_rating: number | null
}

export interface PortalHomework {
  id: number
  title: string
  body: string | null
  due_at: string | null
  status: 'assigned' | 'submitted' | 'checked' | string
  grade: number | null
  teacher_comment: string | null
  answer: string | null
  file_url: string | null
}

export interface PortalPayments {
  lessons_left: number
  money_balance: number
  debt_lessons: number
  lesson_price: number | null
  blocked: boolean
  items: { id: number; paid_at: string; category: string; amount: number; lessons: number; method: string; refunded: number; note: string | null }[]
}

export interface PortalTest {
  id: number
  title: string
  kind: string
  score: number
  max_score: number
  finished_at: string
}

export const portalApi = {
  me: () => http.get<PortalMe>('/portal/me'),
  schedule: (id: number, p: { start?: string; days?: number } = {}) => http.get<PortalLesson[]>(`/portal/students/${id}/schedule${qs(p)}`),
  attendance: (id: number) => http.get<{ items: PortalMark[]; month: { lessons: number; present: number; rate: number | null } }>(`/portal/students/${id}/attendance`, { silent: true }),
  homework: (id: number) => http.get<PortalHomework[]>(`/portal/students/${id}/homework`, { silent: true }),
  submit: (hwId: number, body: { student_id: number; answer?: string | null; file_key?: string | null }) =>
    http.post<{ status: string }>(`/portal/homework/${hwId}/submit`, body, { silent: true }),
  payments: (id: number) => http.get<PortalPayments>(`/portal/students/${id}/payments`),
  tests: (id: number) => http.get<PortalTest[]>(`/portal/students/${id}/tests`, { silent: true }),
  rate: (lessonId: number, body: { student_id: number; stars: number; comment?: string | null }) =>
    http.post<{ stars: number }>(`/portal/lessons/${lessonId}/rate`, body, { silent: true }),
}
