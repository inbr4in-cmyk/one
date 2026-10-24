import { http, qs } from './http'

export interface ChatUser {
  id: number
  full_name: string
  kind: 'staff' | 'student' | 'parent'
  position: string | null
  /** Role and group, e.g. «Ученик, IELTS-1», to tell namesakes apart */
  subtitle?: string | null
}

export interface Chat {
  id: number
  kind: 'group' | 'direct'
  title: string
  group_id: number | null
  unread: number
  last_message: { text: string; at: string; sender: string | null } | null
  other_user: ChatUser | null
  members: number
}

export interface ChatMessage {
  id: number
  chat_id: number
  sender_id: number
  sender_name: string | null
  sender_kind: string | null
  at: string
  kind: 'text' | 'image' | 'file' | 'voice'
  text: string | null
  file_url: string | null
  file_name: string | null
  pinned: boolean
  edited: boolean
  hidden: boolean
}

export interface UploadedFile {
  key: string
  url: string
  name: string
  size: number
}

export interface Notice {
  id: number
  at: string
  kind: string
  title: string
  body: string | null
  link: string | null
  read: boolean
}

export interface Counters {
  notifications: number
  chats?: number
  inbox?: number
  /** New leads nobody has answered yet */
  crm?: number
  /** My open tasks */
  tasks?: number
}

export const chatsApi = {
  list: () => http.get<Chat[]>('/chats'),
  monitor: (p: { branch_id?: number | null; kind?: string } = {}) => http.get<Chat[]>(`/chats/monitor${qs(p)}`),
  contacts: (q?: string) => http.get<ChatUser[]>(`/chats/contacts${qs({ q })}`),
  direct: (user_id: number) => http.post<Chat>('/chats/direct', { user_id }),
  messages: (id: number, p: { before_id?: number; after_id?: number } = {}) =>
    http.get<ChatMessage[]>(`/chats/${id}/messages${qs(p)}`),
  send: (id: number, body: { text?: string | null; file_key?: string | null; file_name?: string | null; kind?: ChatMessage['kind'] }) =>
    http.post<ChatMessage>(`/chats/${id}/messages`, body),
  read: (id: number) => http.post<null>(`/chats/${id}/read`, undefined, { silent: true }),
  pin: (messageId: number) => http.post<ChatMessage>(`/chat-messages/${messageId}/pin`),
  pinned: (id: number) => http.get<ChatMessage[]>(`/chats/${id}/pinned`, { silent: true }),
  hide: (messageId: number) => http.delete(`/chat-messages/${messageId}`),
  upload: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return http.post<UploadedFile>('/files', fd)
  },
}

export const notifyApi = {
  list: () => http.get<{ unread: number; items: Notice[] }>('/notifications?limit=30', { silent: true }),
  readAll: () => http.post<null>('/notifications/read-all', undefined, { silent: true }),
  counters: () => http.get<Counters>('/counters', { silent: true }),
  wsTicket: () => http.post<{ ticket: string }>('/ws/ticket', undefined, { silent: true }),
}

export interface SearchHit {
  id: number
  title: string
  status?: string
  source?: string
  branch_id?: number
  position?: string | null
}
export interface SearchOut {
  students?: SearchHit[]
  leads?: SearchHit[]
  groups?: SearchHit[]
  staff?: SearchHit[]
}
export const searchApi = {
  search: (q: string, signal?: AbortSignal) => http.get<SearchOut>(`/search${qs({ q })}`, { silent: true, signal }),
}
