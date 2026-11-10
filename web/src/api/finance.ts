import { download, http, qs } from './http'
import type { Page } from './org'

/** GET /dashboard — money fields only come back to users who may see finance or payments. */
export interface Dashboard {
  period: string
  revenue_today?: number
  revenue_month?: number
  revenue_trend?: { period: string; revenue: number }[]
  sales_month?: number
  students_active: number
  students_left?: number
  students_frozen?: number
  left_month?: number
  debtors: number
  low_balance: number
  lessons_today: number
  attendance_rate: number | null
  leads_month?: number
  conversion?: number | null
  leads_by_source?: Record<string, number>
}

export interface Ratings {
  period: string
  teachers: { user_id: number; full_name: string | null; lessons: number; marks: number; attendance_rate: number | null; avg_students: number }[]
  sales: { user_id: number; full_name: string | null; trial_visit?: number; sale?: number; return?: number; trial_retention?: number }[]
}

export interface PnlRow {
  branch_id: number
  branch: string
  revenue: Record<string, number>
  refunds: number
  net_revenue: number
  expenses: Record<string, number>
  payroll: number
  total_expenses: number
  profit: number
  margin: number | null
}

export interface Pnl {
  period: string
  branches: PnlRow[]
  total: { refunds: number; net_revenue: number; payroll: number; total_expenses: number; profit: number; margin: number | null }
}

export interface ExpenseCategory {
  id: number
  code: string
  name: string
}

export interface Expense {
  id: number
  branch_id: number | null
  category_id: number
  amount: number
  spent_on: string
  note: string | null
  receipt_url: string | null
  recurring: boolean
  recurring_day: number | null
  /** Set for expenses the system writes (book purchases, shop): edited in their own section */
  source_ref: string | null
  created_by: number | null
}

export interface ExpenseIn {
  branch_id: number | null
  category_id: number
  amount: number
  spent_on: string
  note?: string | null
  recurring?: boolean
  recurring_day?: number | null
}

type BranchQ = { branch_id?: number | null }

export const financeApi = {
  dashboard: (p: BranchQ & { period?: string } = {}) => http.get<Dashboard>(`/dashboard${qs(p)}`),
  ratings: (p: BranchQ & { period?: string } = {}) => http.get<Ratings>(`/payroll/ratings${qs(p)}`, { silent: true }),
  pnl: (p: BranchQ & { period: string }) => http.get<Pnl>(`/finance/pnl${qs(p)}`),
  categories: () => http.get<ExpenseCategory[]>('/expense-categories'),
  createCategory: (body: { name: string; code?: string }) => http.post<ExpenseCategory>('/expense-categories', body, { silent: true }),
  renameCategory: (id: number, name: string) => http.patch<ExpenseCategory>(`/expense-categories/${id}`, { name }),
  archiveCategory: (id: number) => http.post<void>(`/expense-categories/${id}/archive`),
  expenses: (p: BranchQ & { period?: string; category_id?: number | null; limit?: number; offset?: number }) =>
    http.get<Page<Expense>>(`/expenses${qs(p)}`),
  createExpense: (body: ExpenseIn) => http.post<Expense>('/expenses', body, { silent: true }),
  updateExpense: (id: number, body: ExpenseIn) => http.patch<Expense>(`/expenses/${id}`, body, { silent: true }),
  archiveExpense: (id: number) => http.post<null>(`/expenses/${id}/archive`),
  exportPayments: (p: BranchQ & { period: string }) => download(`/finance/export/payments.xlsx${qs(p)}`, `payments-${p.period}.xlsx`),
  exportPnl: (p: BranchQ & { period: string }) => download(`/finance/export/pnl.xlsx${qs(p)}`, `pnl-${p.period}.xlsx`),
}
