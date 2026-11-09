import { http, qs } from './http'
import type { Page } from './org'

export type StudentStatus = 'lead' | 'trial' | 'active' | 'frozen' | 'finished' | 'left'
export const STUDENT_STATUSES: StudentStatus[] = ['active', 'trial', 'lead', 'frozen', 'finished', 'left']

export interface StudentListItem {
  id: number
  full_name: string
  phone: string | null
  branch_id: number
  level_id: number | null
  status: StudentStatus
  group_names: string[]
  lessons_left: number
  money_balance: number
  last_payment_at: string | null
  last_visit_at: string | null
  age: number | null
}

export interface Guardian {
  id: number
  user_id: number
  full_name: string
  phone: string | null
  relation: string | null
  notify: boolean
}

export interface StudentGroupRef {
  id: number
  name: string
  joined_on: string
  left_on: string | null
  level_id: number
  teacher_id: number
}

export interface Student extends StudentListItem {
  birth_date: string | null
  photo_url: string | null
  source: string | null
  notes: string | null
  contract_no?: string | null
  contract_date?: string | null
  sales_user_id: number | null
  office_user_id: number | null
  user_id: number | null
  stars: number
  coins: number
  balance: { lessons_paid: number; lessons_done: number; lessons_left: number; money_balance: number; lesson_price: number }
  guardians: Guardian[]
  groups: StudentGroupRef[]
  created_at: string
  archived_at: string | null
}

export interface LedgerEntry {
  id: number
  at: string
  kind: string
  lessons_delta: number
  money_delta: number
  lesson_price: number
  lessons_after: number
  money_after: number
  note: string | null
}

export interface GuardianIn {
  full_name: string
  phone: string
  relation?: string | null
  notify?: boolean
  locale?: 'ru' | 'kk'
}

export interface StudentIn {
  full_name: string
  birth_date?: string | null
  phone?: string | null
  branch_id: number
  level_id?: number | null
  source?: string | null
  notes?: string | null
  guardians: GuardianIn[]
  create_account: boolean
  contract_no?: string | null
  contract_date?: string | null
}

export interface TransferPreview {
  from_group: string | null
  to_group: string
  from_level: string | null
  to_level: string
  same_price: boolean
  lessons_before: number
  money_before: number
  old_price: number
  new_price: number
  value: number
  lessons_after: number
  money_after: number
  book_hint: string | null
}

export interface Attempt {
  id: number
  test_id: number
  auto_score: number
  manual_score: number | null
  score: number
  status: string
  recommended_level_id: number | null
  test_title: string | null
  test_kind: string | null
  max_score: number | null
  finished_at: string | null
}

/** GET /students/{id}/attendance: newest first. */
export interface AttendanceMark {
  lesson_id: number
  at: string
  group: string | null
  status: 'present' | 'absent' | 'late' | 'excused'
  charged: boolean
  grade: number | null
  comment: string | null
}

export interface StudentFilters {
  q?: string
  branch_id?: number | null
  status?: string
  level_id?: number | null
  group_id?: number | null
  debt?: boolean
  limit?: number
  offset?: number
}

export const studentsApi = {
  list: (f: StudentFilters) => http.get<Page<StudentListItem>>(`/students${qs({ ...f })}`),
  get: (id: number) => http.get<Student>(`/students/${id}`),
  create: (body: StudentIn) => http.post<Student>('/students', body),
  update: (id: number, body: Partial<StudentIn>) => http.patch<Student>(`/students/${id}`, body),
  addGuardian: (id: number, g: GuardianIn) => http.post<Student>(`/students/${id}/guardians`, g),
  ledger: (id: number) => http.get<LedgerEntry[]>(`/students/${id}/ledger`),
  transferPreview: (id: number, to_group_id: number) =>
    http.post<TransferPreview>(`/students/${id}/transfer/preview`, { to_group_id }),
  transfer: (id: number, to_group_id: number, reason: string | null) =>
    http.post<Student>(`/students/${id}/transfer`, { to_group_id, reason }),
  freeze: (id: number, starts_on: string, ends_on: string, reason: string | null) =>
    http.post<Student>(`/students/${id}/freeze`, { starts_on, ends_on, reason }),
  unfreeze: (id: number) => http.post<Student>(`/students/${id}/unfreeze`),
  archive: (id: number) => http.post<null>(`/students/${id}/archive`),
  tests: (id: number) => http.get<Attempt[]>(`/students/${id}/tests`, { silent: true }),
  attendance: (id: number) => http.get<AttendanceMark[]>(`/students/${id}/attendance`, { silent: true }),
}
