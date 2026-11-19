import { http } from './http'

export interface ProfilePlace { place: string; role: string | null; year_from: number | null; year_to: number | null }
export interface ProfileAward { title: string; year: number | null; file_key: string | null; file_name: string | null; file_url?: string | null }
export interface StaffProfile {
  user_id: number
  full_name: string
  position: string | null
  roles: string[]
  branches: string[]
  photo_key: string | null
  photo_url: string | null
  phone: string | null
  email: string | null
  about: string | null
  education: ProfilePlace[]
  experience: ProfilePlace[]
  awards: ProfileAward[]
  show_contacts: boolean
  can_edit: boolean
}
export interface ProfileIn {
  photo_key: string | null
  email: string | null
  about: string | null
  education: ProfilePlace[]
  experience: ProfilePlace[]
  awards: Omit<ProfileAward, 'file_url'>[]
  show_contacts: boolean
}

export const profileApi = {
  get: (id: number) => http.get<StaffProfile>(`/profiles/${id}`),
  save: (id: number, body: ProfileIn) => http.put<StaffProfile>(`/profiles/${id}`, body),
}
