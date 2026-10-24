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
  contact: { id: number; name: string | null; username: string | null; phone: string | null; student_id: number | null }
  lead: { id: number; full_name: string; stage: string | null; stage_code: string | null; source: string } | null
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
}

export const inboxApi = {
  list: (p: { channel?: Channel | ''; status?: string; unread?: boolean; mine?: boolean; q?: string }) =>
    http.get<Conversation[]>(`/inbox/conversations${qs(p)}`),
  get: (id: number) => http.get<Conversation>(`/inbox/conversations/${id}`),
  messages: (id: number, before_id?: number) => http.get<InboxMessage[]>(`/inbox/conversations/${id}/messages${qs({ before_id })}`),
  reply: (id: number, text: string) => http.post<InboxMessage>(`/inbox/conversations/${id}/messages`, { text }, { silent: true }),
  template: (id: number, code: string, variables: Record<string, string>) =>
    http.post<InboxMessage>(`/inbox/conversations/${id}/template`, { code, variables }),
  patch: (id: number, body: { status?: 'open' | 'closed'; assignee_id?: number | null; branch_id?: number | null }) =>
    http.patch<Conversation>(`/inbox/conversations/${id}`, body),
}
