import { http, qs } from './http'

export interface MyCheckin {
  in_at: string | null
  out_at: string | null
  branch_id: number | null
}

export interface CheckinRow {
  user_id: number
  full_name: string
  branch_id: number
  in_at: string
  out_at: string | null
}

export interface DailyReport {
  user_id: number
  full_name: string
  text: string
  updated_at: string
}

export interface Course {
  id: number
  title: string
  description: string | null
  role_codes: string[]
  materials: number
  done: number
}

export interface Material {
  id: number
  kind: 'video' | 'document' | 'test'
  title: string
  url: string | null
  body: string | null
  test_id: number | null
  done_at: string | null
  score: number | null
}

export interface CourseDetail extends Omit<Course, 'materials' | 'done'> {
  materials: Material[]
}

export interface ProgressRow {
  user_id: number
  full_name: string
  position: string | null
  courses: { course_id: number; title: string | null; done: number; total: number }[]
}

export const workApi = {
  me: () => http.get<MyCheckin>('/checkin/me', { silent: true }),
  checkIn: (branch_id: number) => http.post<{ id: number; in_at: string }>('/checkin', { branch_id }),
  checkOut: () => http.post<{ in_at: string; out_at: string }>('/checkout'),
  checkins: (p: { day?: string; branch_id?: number | null }) => http.get<CheckinRow[]>(`/checkins${qs(p)}`),
  /** My report for today, to prefill the form */
  myReport: () => http.get<{ day: string; text: string | null; updated_at: string | null }>('/daily-report', { silent: true }),
  report: (text: string) => http.put<{ day: string }>('/daily-report', { text }, { silent: true }),
  reports: (day?: string) => http.get<DailyReport[]>(`/daily-reports${qs({ day })}`),
  courses: () => http.get<Course[]>('/training/courses'),
  course: (id: number) => http.get<CourseDetail>(`/training/courses/${id}`, { silent: true }),
  createCourse: (body: { title: string; description?: string | null; role_codes: string[] }) => http.post<{ id: number }>('/training/courses', body, { silent: true }),
  addMaterial: (courseId: number, body: { kind: 'video' | 'document'; title: string; url?: string | null; body?: string | null; order?: number }) =>
    http.post<{ id: number }>(`/training/courses/${courseId}/materials`, body, { silent: true }),
  done: (materialId: number) => http.post<{ done_at: string; score: number | null }>(`/training/materials/${materialId}/done`, {}),
  progress: () => http.get<ProgressRow[]>('/training/progress'),
}
