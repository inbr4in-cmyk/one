import { http, qs, download } from './http'
import type { Scope } from './auth'
import type { Page } from './org'

/** module → { title, actions: { action: title } } */
export type PermissionCatalog = Record<string, { title: string; actions: Record<string, string> }>

export interface Role {
  id: number
  name: string
  code: string
  description: string | null
  is_system: boolean
  coin_limit: number
  archived_at: string | null
  permissions: { module: string; action: string; scope: Scope }[]
  members: number
}

export interface RoleIn {
  name: string
  description?: string | null
  coin_limit: number
  permissions: { module: string; action: string; scope: Scope }[]
}

export interface Staff {
  id: number
  full_name: string
  phone: string | null
  position: string | null
  salary: number | null
  is_active: boolean
  totp_enabled: boolean
  last_login_at: string | null
  roles: { id: number; name: string; code: string }[]
  branch_ids: number[]
  archived_at: string | null
}

export interface StaffIn {
  full_name: string
  phone: string
  email?: string | null
  position?: string | null
  salary?: number
  password?: string | null
  role_ids: number[]
  branch_ids: number[]
}

export interface AuditRow {
  id: number
  at: string
  actor_id: number | null
  actor_name: string | null
  action: string
  entity: string
  entity_id: number | null
  branch_id: number | null
  before: Record<string, unknown>
  after: Record<string, unknown>
  ip: string | null
  note: string | null
}

export interface Rate {
  key: string
  value: number
  effective_from: string
}

export interface ImportPreview {
  preview: { row: number; full_name: string; phone: string | null; birth_date: string | null; branch_id: number; level_id: number | null; group_id: number | null; lessons_left: number; lesson_price: number; parent_name: string | null; parent_phone: string | null }[]
  valid: number
  errors: { row: number; error: string }[]
}

export const adminApi = {
  catalog: () => http.get<PermissionCatalog>('/permissions/catalog'),
  roles: () => http.get<Role[]>('/roles'),
  /** Roles I may give when hiring or editing staff (none wider than my own rights) */
  assignableRoles: () => http.get<AssignableRole[]>('/roles/assignable', { silent: true }),
  createRole: (body: RoleIn) => http.post<Role>('/roles', body, { silent: true }),
  updateRole: (id: number, body: RoleIn) => http.put<Role>(`/roles/${id}`, body, { silent: true }),
  archiveRole: (id: number) => http.post<null>(`/roles/${id}/archive`),
  staff: (p: { q?: string; branch_id?: number | null; role?: string; archived?: boolean; limit?: number; offset?: number }) =>
    http.get<Page<Staff>>(`/staff${qs(p)}`),
  createStaff: (body: StaffIn) => http.post<Staff>('/staff', body, { silent: true }),
  updateStaff: (id: number, body: Partial<Omit<StaffIn, 'phone' | 'password'>> & { is_active?: boolean; phone?: string }) =>
    http.patch<Staff>(`/staff/${id}`, body, { silent: true }),
  archiveStaff: (id: number) => http.post<null>(`/staff/${id}/archive`, undefined, { silent: true }),
  /** Changing your own password needs the current one (`old_password`). */
  setPassword: (id: number, password: string, oldPassword?: string) =>
    http.post<null>(`/staff/${id}/password`, oldPassword ? { password, old_password: oldPassword } : { password }, { silent: true }),
  reset2fa: (id: number) => http.post<null>(`/staff/${id}/reset-2fa`),
  audit: (p: { entity?: string; actor_id?: number | null; action?: string; since?: string; limit?: number; offset?: number }) =>
    http.get<Page<AuditRow>>(`/audit${qs(p)}`),
  settings: () => http.get<Record<string, unknown>>('/settings'),
  putSetting: (key: string, value: unknown) => http.put<null>(`/settings/${key}`, { value }, { silent: true }),
  rates: () => http.get<Rate[]>('/rates'),
  addRate: (body: Rate) => http.post<Rate>('/rates', body, { silent: true }),
  importTemplate: () => download('/import/students/template.xlsx', 'students-template.xlsx'),
  importStudents: (file: File, commit: boolean) => {
    const fd = new FormData()
    fd.append('file', file)
    return http.post<ImportPreview & { created?: number }>(`/import/students${qs({ commit })}`, fd, { silent: true })
  },
}

export interface AssignableRole {
  id: number
  code: string
  name: string
  description?: string | null
}
