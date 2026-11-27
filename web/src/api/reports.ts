import { download, http, qs } from './http'

export interface ReportFilter { date_from: string; date_to: string; branch_id?: number | null; manager_id?: number | null; teacher_id?: number | null }
export interface ManagerRow {
  user_id: number; name: string; new: number; worked: number; actions: number; trial_booked: number; trial_done: number; paid: number
  lost: number; conversion: number | null; tasks_done: number; tasks_overdue: number; sales: number; sales_sum: number; bonus: number
}
export interface TeacherRow {
  user_id: number; name: string; planned: number; held: number; held_pct: number | null; not_marked: number; cancelled: number; subs: number
  plan_pct: number | null; attendance_pct: number | null; pay_lessons: number; pay_other: number; pay_total: number
}
export interface Report<R> { period: [string, string]; rows: R[]; total: Partial<R>; people: { id: number; name: string }[] }

/** «Отчёты»: administrators only (the server checks) */
export const reportsApi = {
  managers: (f: ReportFilter) => http.get<Report<ManagerRow>>(`/reports/managers${qs({ ...f })}`),
  teachers: (f: ReportFilter) => http.get<Report<TeacherRow>>(`/reports/teachers${qs({ ...f })}`),
  managersXlsx: (f: ReportFilter) => download(`/reports/managers.xlsx${qs({ ...f })}`, 'managers.xlsx'),
  teachersXlsx: (f: ReportFilter) => download(`/reports/teachers.xlsx${qs({ ...f })}`, 'teachers.xlsx'),
}
