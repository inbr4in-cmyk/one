import { http, qs } from './http'
import type { Page } from './org'

export type PaymentMethod = 'cash' | 'card' | 'kaspi' | 'transfer' | 'online'
export const PAYMENT_METHODS: PaymentMethod[] = ['kaspi', 'cash', 'card', 'transfer', 'online']

export interface PaymentIn {
  student_id: number
  lessons: number
  method: PaymentMethod
  discount?: number
  promo_code?: string | null
  note?: string | null
  level_id?: number | null
  /** ISO date; only for owners and branch admins (finance.edit) entering an earlier payment */
  paid_on?: string | null
}

export interface Quote {
  lessons: number
  lesson_price: number
  gross: number
  discount: number
  money_balance_used: number
  to_pay: number
}

export interface Payment {
  id: number
  student_id: number
  branch_id: number
  level_id: number | null
  category: string
  amount: number
  discount: number
  lessons: number
  lesson_price: number
  method: PaymentMethod
  received_by: number
  paid_at: string
  refunded: number
  is_first: boolean
  note: string | null
  student_name: string | null
  /** The student's current balance, so a refund never defaults to more than is left */
  student_lessons_left?: number | null
}

export const paymentsApi = {
  quote: (body: PaymentIn) => http.post<Quote>('/payments/quote', body),
  /** `key`: Idempotency-Key, one per payment form, so a retried or double submit records one payment (QA C-1). */
  create: (body: PaymentIn, key: string) => http.post<Payment>('/payments', body, { headers: { 'Idempotency-Key': key } }),
  refundable: (id: number) => http.get<{ lessons_max: number; amount_max: number; amount_left: number }>(`/payments/${id}/refundable`, { silent: true }),
  list: (p: { student_id?: number; branch_id?: number | null; date_from?: string; date_to?: string; limit?: number; offset?: number }) =>
    http.get<Page<Payment>>(`/payments${qs(p)}`),
  refund: (id: number, body: { lessons: number; amount: number; reason: string }) =>
    http.post<{ refund_id: number; bonuses_reversed: number }>(`/payments/${id}/refund`, body, { silent: true }),
}
