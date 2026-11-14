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

export const payrollApi = {
  timesheet: (period: string, branch_id: number) => http.get<Timesheet>(`/payroll/timesheet${qs({ period, branch_id })}`),
  setDays: (body: { user_id: number; branch_id: number; days: string[]; status: DayStatus | null }) =>
    http.put<{ ok: boolean }>('/payroll/timesheet', body, { silent: true }),
  sheet: (p: { period: string; branch_id?: number | null }) => http.get<PayrollSheet>(`/payroll${qs(p)}`),
  accruals: (p: { period: string; user_id?: number; branch_id?: number | null }) => http.get<Accrual[]>(`/payroll/accruals${qs(p)}`),
  my: (period: string) => http.get<{ period: string; total: number; rates_total: number; salary_total: number; items: Accrual[]; breakdown?: PayBreakdown }>(`/payroll/my${qs({ period })}`),
  breakdown: (p: { period: string; user_id: number; branch_id?: number | null }) => http.get<PayBreakdown>(`/payroll/breakdown${qs(p)}`, { silent: true }),
  adjust: (body: AdjustIn) => http.post<Accrual>('/payroll/adjust', body, { silent: true }),
  approve: (period: string, branch_id: number) => http.post<{ status: PeriodStatus; total: number }>('/payroll/periods/approve', { period, branch_id }, { silent: true }),
  paid: (period: string, branch_id: number) => http.post<{ status: PeriodStatus }>('/payroll/periods/paid', { period, branch_id }, { silent: true }),
}
