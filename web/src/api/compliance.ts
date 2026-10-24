import { http, qs } from './http'

export type ComplaintStatus = 'new' | 'acknowledged' | 'investigating' | 'answered' | 'closed' | 'appealed'

export interface Complaint {
  id: number
  subject: string
  body: string
  status: ComplaintStatus
  created_at: string
  acknowledged_at: string | null
  due_at: string
  answer: string | null
  answered_at: string | null
  branch_id: number | null
  file_url: string | null
  /** Handler view only */
  author_id?: number
  against_user_id?: number | null
  overdue?: boolean
}

export type DocKind = 'rules' | 'recording'

export interface DocumentVersion {
  id: number
  kind: DocKind
  version: string
  title: string
  body: string
  effective_from: string
  upcoming: { version: string; effective_from: string } | null
}

export const complaintsApi = {
  create: (body: { subject: string; body: string; against_user_id?: number | null; file_url?: string | null }) =>
    http.post<Complaint>('/complaints', body, { silent: true }),
  my: () => http.get<Complaint[]>('/complaints/my'),
  list: (status?: ComplaintStatus | '') => http.get<Complaint[]>(`/complaints${qs({ status })}`),
  act: (id: number, action: 'acknowledge' | 'investigate' | 'answer' | 'close' | 'appeal', answer?: string) =>
    http.post<Complaint>(`/complaints/${id}`, { action, answer }, { silent: true }),
}

export const docsApi = {
  /** 404 when the school has not published this document yet */
  get: (kind: DocKind) => http.get<DocumentVersion>(`/documents/${kind}`, { silent: true }),
  publish: (body: { kind: DocKind; version: string; title: string; body: string; effective_from: string }) =>
    http.post<{ id: number }>('/documents', body, { silent: true }),
  accept: (document_id: number, student_id?: number | null) =>
    http.post<{ accepted_at: string; version: string }>('/consents', { document_id, student_id: student_id ?? null }),
  missing: (branch_id?: number | null) => http.get<{ student_id: number; full_name: string; branch_id: number }[]>(`/consents/status${qs({ branch_id })}`),
}
