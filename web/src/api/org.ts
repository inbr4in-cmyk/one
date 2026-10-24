import { http, qs } from './http'

export interface Branch {
  id: number
  name: string
  address: string | null
  phone: string | null
  hours: string | null
  admin_id: number | null
}

export interface Room {
  id: number
  branch_id: number
  name: string
  capacity: number
  equipment: string | null
  status: 'active' | 'repair'
}

export interface Level {
  id: number
  name: string
  code: string
  color: string
  lesson_price: number
  order: number
  track: 'adults' | 'kids' | 'exam'
  duration_months: number
  next_level_id: number | null
  is_kids: boolean
}

export interface StaffMember {
  id: number
  full_name: string
  phone: string | null
  position: string | null
  is_active: boolean
  roles: { id: number; code: string; name: string }[]
  branch_ids: number[]
}

export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export const orgApi = {
  branches: () => http.get<Branch[]>('/branches', { silent: true }),
  rooms: (branchId: number) => http.get<Room[]>(`/branches/${branchId}/rooms`),
  levels: () => http.get<Level[]>('/levels'),
  staff: (p: { role?: string; branch_id?: number; q?: string; limit?: number } = {}) =>
    http.get<Page<StaffMember>>(`/staff${qs({ limit: 200, ...p })}`, { silent: true }),
}
