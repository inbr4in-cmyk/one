import { http, qs } from './http'

/** «Оценки и анкеты» (backend/app/modules/assessment/forms.py). */
export type FormQKind = 'short' | 'para' | 'phone' | 'select' | 'single' | 'multi' | 'scale' | 'branch' | 'teacher'
export interface FormOption { text: string; goto?: string; alert?: boolean }
export interface FormQuestion {
  id: string
  text: string
  kind: FormQKind
  required: boolean
  options?: FormOption[]
  other?: boolean
  min?: number
  max?: number
  low?: string
  high?: string
}
export interface FormSection { id: string; title: string; text: string | null; next?: string; questions: FormQuestion[] }
export interface PublicForm {
  title: string
  closed?: boolean
  description: string | null
  thanks: string | null
  active: boolean
  sections: FormSection[]
  branches: { id: number; name: string }[]
  teachers: { id: number; name: string; branch_ids: number[] }[]
}
export type FormValue = number | string | { picked: number[]; other: string | null } | null
export type FormAnswers = Record<string, FormValue>

export interface FormInfo { id: number; title: string; description: string | null; is_open: boolean; is_active: boolean; path: string; questions: number; sections: number; total: number; new: number }
export interface FormRow {
  id: number
  at: string
  name: string | null
  phone: string | null
  branch_id: number | null
  branch: string | null
  teacher: string | null
  flags: string[]
  status: 'new' | 'done'
  note: string | null
  done_at: string | null
  kind: string | null
  sections?: { title: string; items: { text: string; value: string; low: boolean }[] }[]
}
export interface FormSummary {
  date_from: string
  date_to: string
  count: number
  questions: ({ id: string; section: string; text: string } & ({ kind: 'choice'; options: { text: string; total: number; by_branch: Record<string, number> }[] } | { kind: 'scale'; count: number; avg: number | null }))[]
}

export const formsApi = {
  list: () => http.get<FormInfo[]>('/forms', { silent: true }),
  patch: (id: number, body: { is_open?: boolean; is_active?: boolean }) => http.patch<FormInfo>(`/forms/${id}`, body),
  responses: (id: number, p: { status?: string; branch_id?: number } = {}) => http.get<FormRow[]>(`/forms/${id}/responses${qs(p)}`),
  response: (id: number) => http.get<FormRow>(`/form-responses/${id}`),
  done: (id: number, body: { done: boolean; note: string | null }) => http.post<FormRow>(`/form-responses/${id}/done`, body),
  summary: (id: number) => http.get<FormSummary>(`/forms/${id}/summary`),
  publicGet: (token: string) => http.get<PublicForm>(`/public/forms/${token}`, { auth: false, silent: true }),
  publicSend: (token: string, answers: FormAnswers) => http.post<{ thanks: string | null }>(`/public/forms/${token}`, { answers }, { auth: false, silent: true }),
  myList: () => http.get<{ title: string; path: string }[]>('/my/forms', { silent: true }),
  myGet: (token: string) => http.get<PublicForm>(`/my/forms/${token}`, { silent: true }),
  mySend: (token: string, answers: FormAnswers) => http.post<{ thanks: string | null }>(`/my/forms/${token}`, { answers }, { silent: true }),
}
