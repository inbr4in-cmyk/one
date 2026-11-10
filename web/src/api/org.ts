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

export type BranchIn = Omit<Branch, 'id'>
export type RoomIn = Omit<Room, 'id' | 'branch_id'>

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

export interface LevelIn {
  name: string
  code?: string | null
  color: string
  lesson_price: number
  order: number
  track: 'adults' | 'kids' | 'exam'
  duration_months: number
  next_level_id: number | null
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

/** GET /staff-directory: a light list of colleagues for pickers, open to any staff member. */
export interface DirectoryEntry {
  id: number
  full_name: string
  position: string | null
  branch_ids: number[]
  roles: string[]
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
  createBranch: (body: BranchIn) => http.post<Branch>('/branches', body),
  updateBranch: (id: number, body: BranchIn) => http.patch<Branch>(`/branches/${id}`, body),
  createRoom: (branchId: number, body: RoomIn) => http.post<Room>(`/branches/${branchId}/rooms`, body),
  updateRoom: (id: number, body: RoomIn) => http.patch<Room>(`/rooms/${id}`, body),
  archiveRoom: (id: number) => http.post<void>(`/rooms/${id}/archive`, {}),
  levels: () => http.get<Level[]>('/levels'),
  createLevel: (body: LevelIn) => http.post<Level>('/levels', body),
  updateLevel: (id: number, body: LevelIn) => http.patch<Level>(`/levels/${id}`, body),
  archiveLevel: (id: number) => http.post<void>(`/levels/${id}/archive`),
  directory: (p: { role?: string; branch_id?: number } = {}) => http.get<DirectoryEntry[]>(`/staff-directory${qs(p)}`, { silent: true }),
  staff: (p: { role?: string; branch_id?: number; q?: string; limit?: number } = {}) =>
    http.get<Page<StaffMember>>(`/staff${qs({ limit: 200, ...p })}`, { silent: true }),
}
