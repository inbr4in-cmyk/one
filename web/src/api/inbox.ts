import { http, qs } from './http'

export type Channel = 'instagram' | 'whatsapp'

export interface Conversation {
  id: number
  channel: Channel
  branch_id: number | null
  assignee_id: number | null
  unread: number
  status: 'open' | 'closed'
  last_message_at: string | null
  last_preview: string | null
  in_window: boolean
  /** WhatsApp linked by QR: answers have no 24 h rule */
  free_reply?: boolean
  contact: { id: number; name: string | null; username: string | null; phone: string | null; student_id: number | null }
  lead: { id: number; full_name: string; stage: string | null; stage_code: string | null; source: string } | null
  student: { id: number; full_name: string } | null
}

export interface InboxMessage {
  id: number
  at: string
  direction: 'in' | 'out'
  kind: string
  text: string | null
  media_url: string | null
  status: string
  sender_id: number | null
  sender_name?: string | null
}

/** GET /message-templates: WhatsApp templates allowed outside the 24 h window. */
export interface MessageTemplate {
  code: string
  locale: 'ru' | 'kk'
  body: string
  variables: string[]
}

export const inboxApi = {
  templates: () => http.get<MessageTemplate[]>('/message-templates'),
  list: (p: { channel?: Channel | ''; status?: string; unread?: boolean; mine?: boolean; q?: string }) =>
    http.get<Conversation[]>(`/inbox/conversations${qs(p)}`),
  get: (id: number) => http.get<Conversation>(`/inbox/conversations/${id}`),
  messages: (id: number, before_id?: number) => http.get<InboxMessage[]>(`/inbox/conversations/${id}/messages${qs({ before_id })}`),
  reply: (id: number, text: string) => http.post<InboxMessage>(`/inbox/conversations/${id}/messages`, { text }, { silent: true }),
  template: (id: number, code: string, variables: Record<string, string>, locale: 'ru' | 'kk') =>
    http.post<InboxMessage>(`/inbox/conversations/${id}/template`, { code, variables, locale }),
  linkStudent: (id: number, student_id: number) => http.post<Conversation>(`/inbox/conversations/${id}/link-student`, { student_id }),
  patch: (id: number, body: { status?: 'open' | 'closed'; assignee_id?: number | null; branch_id?: number | null }) =>
    http.patch<Conversation>(`/inbox/conversations/${id}`, body),
}
