import { http, qs } from './http'
import type { Page } from './org'

export type TaskStatus = 'new' | 'in_progress' | 'review' | 'done' | 'cancelled'
export type TaskPriority = 'low' | 'normal' | 'high'
export type TaskLink = 'student' | 'lead' | 'group' | 'lesson'

export interface Task {
  id: number
  title: string
  description: string | null
  creator_id: number
  creator_name: string | null
  branch_id: number | null
  priority: TaskPriority
  due_at: string | null
  status: TaskStatus
  done_at: string | null
  overdue: boolean
  link_type: TaskLink | null
  link_id: number | null
  recurrence: 'daily' | 'weekly' | null
  assignees: { id: number; full_name: string }[]
  comments: number
  created_at: string
}

export interface TaskIn {
  title: string
  description?: string | null
  branch_id?: number | null
  priority: TaskPriority
  due_at?: string | null
  assignee_ids: number[]
  link_type?: TaskLink | null
  link_id?: number | null
  recurrence?: 'daily' | 'weekly' | null
}

export interface TaskComment {
  id: number
  author_id: number
  author: string
  at: string
  text: string
  file_url: string | null
}

export const tasksApi = {
  list: (p: { box: 'mine' | 'created' | 'all'; status?: TaskStatus | ''; overdue?: boolean; branch_id?: number | null; limit?: number; offset?: number }) =>
    http.get<Page<Task>>(`/tasks${qs(p)}`),
  get: (id: number) => http.get<Task>(`/tasks/${id}`, { silent: true }),
  create: (body: TaskIn) => http.post<Task>('/tasks', body, { silent: true }),
  patch: (id: number, body: Partial<Omit<TaskIn, 'branch_id' | 'link_type' | 'link_id' | 'recurrence'>> & { status?: TaskStatus }) =>
    http.patch<Task>(`/tasks/${id}`, body),
  comments: (id: number) => http.get<TaskComment[]>(`/tasks/${id}/comments`),
  comment: (id: number, text: string) => http.post<{ id: number; at: string }>(`/tasks/${id}/comments`, { text }),
  archive: (id: number) => http.post<null>(`/tasks/${id}/archive`),
}
