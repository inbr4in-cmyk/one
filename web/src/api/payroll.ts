import { http, qs } from './http'

export type PeriodStatus = 'draft' | 'approved' | 'paid'

export interface PayrollPerson {
  user_id: number
  full_name: string
  position: string | null
  pay_scheme: 'rates' | 'salary' | 'both' | null
  by_kind: Record<string, { title: string; amount: number; count: number }>
  total: number
  rates_total: number
  salary_total: number
  /** handed out for the month, and what is left (below zero = the person's debt) */
  paid?: number
  left?: number
}

export interface PayrollSheet {
  period: string
  /** Filled only when a branch is asked for: { [branch_id]: status } */
  status: Record<string, PeriodStatus>
  people: PayrollPerson[]
  total: number
}

export interface Accrual {
  id: number
  user_id: number
  branch_id: number | null
  period: string
  kind: string
  amount: number
  description: string
  ref_type: string | null
  ref_id: number | null
  created_by: number | null
  created_at: string
}

export interface PayLine { key: string; title: string; count: number; amount: number }
export interface PayBreakdown { lessons: PayLine[]; lessons_total: number; lessons_count: number; kpi: PayLine; other: PayLine[]; total: number }

export interface AdjustIn {
  user_id: number
  branch_id: number
  kind: 'bonus' | 'deduction' | 'salary'
  amount: number
  description: string
  period?: string
}

export interface SettlePart { part: 'salary' | 'rate' | 'kpi' | 'bonus' | 'deduction' | 'carry'; title: string; accrued: number; paid: number; left: number; note: string | null }
export interface PayoutBatch { id: number; period: string; paid_on: string; note: string | null; total: number; lines: { part: string; title: string; amount: number }[] }
export interface Settlement { user_id: number; full_name: string; position: string | null; period: string; parts: SettlePart[]; balance: number; payouts: PayoutBatch[] }
export interface PayoutIn {
  user_id: number
  branch_id: number
  period: string
  paid_on?: string | null
  lines: { part: string; amount: number }[]
  bonus?: { amount: number; note: string } | null
  fine?: { amount: number; note: string } | null
}

export type DayStatus = 'work' | 'off' | 'sick' | 'vacation' | 'absent'
export interface TimesheetPerson {
  user_id: number
  full_name: string
  position: string | null
  pay_scheme: 'rates' | 'salary' | 'both' | null
  salary: number | null
  days: Record<string, DayStatus>
  worked: number
  amount: number | null
}
export interface Timesheet { period: string; branch_id: number; norm: number; workdays: number[]; locked: boolean; can_edit: boolean; people: TimesheetPerson[] }

export interface PayPersonLesson { lesson_id: number; day: number; date: string; time: string; amount: number; base: number; kpi: number; note: string }
export interface PayPersonGroup { key: string; group_id: number | null; name: string; kind: string; count: number; amount: number; base: number; kpi: number; lessons: PayPersonLesson[] }
export interface PayPerson {
  user: { id: number; full_name: string; position: string | null; pay_scheme: string | null }
  period: string
  days: number
  groups: PayPersonGroup[]
  lessons_total: number
  rate_total: number
  kpi_total: number
  lessons_count: number
  other: { id: number; kind: string; title: string; amount: number; description: string; created_at: string }[]
  other_total: number
  total: number
  paid: number
  left: number
  payouts: PayoutBatch[]
}

export const payrollApi = {
  timesheet: (period: string, branch_id: number) => http.get<Timesheet>(`/payroll/timesheet${qs({ period, branch_id })}`),
  setDays: (body: { user_id: number; branch_id: number; days: string[]; status: DayStatus | null }) =>
    http.put<{ ok: boolean }>('/payroll/timesheet', body, { silent: true }),
  sheet: (p: { period: string; branch_id?: number | null }) => http.get<PayrollSheet>(`/payroll${qs(p)}`),
  accruals: (p: { period: string; user_id?: number; branch_id?: number | null }) => http.get<Accrual[]>(`/payroll/accruals${qs(p)}`),
  settlement: (p: { user_id: number; branch_id: number; period: string }) => http.get<Settlement>(`/payroll/settlement${qs(p)}`, { silent: true }),
  payOut: (body: PayoutIn) => http.post<Settlement>('/payroll/payouts', body, { silent: true }),
  cancelPayout: (id: number) => http.post<{ ok: boolean }>(`/payroll/payouts/${id}/cancel`, {}, { silent: true }),
  my: (period: string) => http.get<{ period: string; total: number; rates_total: number; salary_total: number; paid?: number; payouts?: PayoutBatch[]; items: Accrual[]; breakdown?: PayBreakdown }>(`/payroll/my${qs({ period })}`),
  person: (p: { period: string; user_id: number; branch_id?: number | null }) => http.get<PayPerson>(`/payroll/person${qs(p)}`, { silent: true }),
  breakdown: (p: { period: string; user_id: number; branch_id?: number | null }) => http.get<PayBreakdown>(`/payroll/breakdown${qs(p)}`, { silent: true }),
  adjust: (body: AdjustIn) => http.post<Accrual>('/payroll/adjust', body, { silent: true }),
  approve: (period: string, branch_id: number) => http.post<{ status: PeriodStatus; total: number }>('/payroll/periods/approve', { period, branch_id }, { silent: true }),
  paid: (period: string, branch_id: number) => http.post<{ status: PeriodStatus }>('/payroll/periods/paid', { period, branch_id }, { silent: true }),
}
