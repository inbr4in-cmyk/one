import { http, qs } from './http'

/** Built-in codes; the school can add its own (s1, s2…) on the Справочники page, so any string is possible. */
export type LeadSource = string
export const LEAD_SOURCES: LeadSource[] = ['instagram', 'whatsapp', 'qr', 'site', 'referral', 'walk_in', 'sales', 'return']

export interface Stage {
  id: number
  code: string
  name: string
  color: string
  order: number
  is_won: boolean
  is_lost: boolean
  stale_after_hours?: number | null
  /** built-in: renamed and recoloured, never removed */
  system?: boolean
}

export interface StageIn {
  name: string
  color: string
  stale_after_hours: number | null
}

export interface Pipeline {
  id: number
  code: string
  name: string
  stages: Stage[]
}

export interface Lead {
  id: number
  full_name: string
  phone: string | null
  age: number | null
  parent_name: string | null
  parent_phone: string | null
  branch_id: number
  pipeline_id: number
  stage_id: number
  stage_changed_at: string
  source: LeadSource
  owner_id: number | null
  owner_name: string | null
  assignee_id: number | null
  student_id: number | null
  level_id: number | null
  placement_score: number | null
  trial_lesson_id: number | null
  trial_at: string | null
  lost_reason: string | null
  next_action_at: string | null
  last_activity_at: string | null
  notes: string | null
  is_hot: boolean
  created_at: string
  stale: boolean
  waiting_min: number | null
  channel: string | null
  conversation_id: number | null
}

export interface BoardColumn {
  stage: Stage
  total: number
  leads: Lead[]
}

export interface Board {
  pipeline: { id: number; code: string; name: string }
  columns: BoardColumn[]
}

export interface LeadEvent {
  id: number
  at: string
  kind: string
  text: string | null
  actor_id: number | null
  meta: Record<string, unknown>
}

export interface LeadDetails {
  lead: Lead
  events: LeadEvent[]
  tests: { id: number; score: number; level_id: number | null; at: string | null }[]
}

export interface LeadIn {
  full_name: string
  phone?: string | null
  branch_id: number
  source: LeadSource
  age?: number | null
  parent_name?: string | null
  parent_phone?: string | null
  level_id?: number | null
  notes?: string | null
}

export interface Funnel {
  new: number
  contacted: number
  trial_booked: number
  trial_done: number
  paid: number
  lost: number
  conversion: number
}

export interface Analytics {
  period: [string, string]
  total: Funnel
  by_source: Record<string, Funnel>
  by_owner: (Funnel & { user_id: number | null; name: string | null })[]
  by_branch: Record<string, Funnel>
  lost_reasons: Record<string, number>
}

export const crmApi = {
  pipelines: () => http.get<Pipeline[]>('/crm/pipelines'),
  addStage: (pipelineId: number, body: StageIn) => http.post<Stage>(`/crm/pipelines/${pipelineId}/stages`, body),
  editStage: (id: number, body: StageIn) => http.patch<Stage>(`/crm/stages/${id}`, body),
  orderStages: (pipelineId: number, ids: number[]) => http.put<Stage[]>(`/crm/pipelines/${pipelineId}/order`, { stage_ids: ids }),
  archiveStage: (id: number) => http.post<void>(`/crm/stages/${id}/archive`),
  board: (p: { pipeline: string; branch_id?: number | null; source?: string; owner_id?: number | null; q?: string }) =>
    http.get<Board>(`/crm/board${qs(p)}`),
  create: (body: LeadIn) => http.post<Lead>('/crm/leads', body),
  get: (id: number) => http.get<LeadDetails>(`/crm/leads/${id}`),
  patch: (id: number, body: Partial<LeadIn> & { is_hot?: boolean; next_action_at?: string | null }) =>
    http.patch<Lead>(`/crm/leads/${id}`, body),
  stage: (id: number, stage_id: number, lost_reason?: string | null, silent = false) =>
    http.post<Lead>(`/crm/leads/${id}/stage`, { stage_id, lost_reason }, { silent }),
  event: (id: number, body: { kind: 'call' | 'note' | 'meeting'; text: string; result?: string | null }) =>
    http.post<LeadEvent>(`/crm/leads/${id}/events`, body),
  trial: (id: number, lesson_id: number, notify = true) => http.post<Lead>(`/crm/leads/${id}/trial`, { lesson_id, notify }),
  convert: (id: number) => http.post<{ student_id: number }>(`/crm/leads/${id}/convert`, { create_account: true }),
  archive: (id: number) => http.post<null>(`/crm/leads/${id}/archive`),
  analytics: (p: { date_from?: string; date_to?: string; branch_id?: number | null }) =>
    http.get<Analytics>(`/crm/analytics${qs(p)}`),
}

/** «Откуда узнал»: built-in and the school's own sources */
export interface SourceItem { code: string; name: string; system: boolean; builtin: boolean; hidden: boolean }
export const sourcesApi = {
  list: () => http.get<SourceItem[]>('/crm/sources', { silent: true }),
  add: (name: string) => http.post<SourceItem>('/crm/sources', { name }),
  rename: (code: string, name: string) => http.patch<SourceItem>(`/crm/sources/${code}`, { name }),
  archive: (code: string) => http.post<void>(`/crm/sources/${code}/archive`, {}),
}
