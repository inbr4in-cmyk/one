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
}

export const paymentsApi = {
  quote: (body: PaymentIn) => http.post<Quote>('/payments/quote', body),
  create: (body: PaymentIn) => http.post<Payment>('/payments', body),
  list: (p: { student_id?: number; branch_id?: number | null; date_from?: string; date_to?: string; limit?: number; offset?: number }) =>
    http.get<Page<Payment>>(`/payments${qs(p)}`),
  refund: (id: number, body: { lessons: number; amount: number; reason: string }) =>
    http.post<{ refund_id: number; bonuses_reversed: number }>(`/payments/${id}/refund`, body, { silent: true }),
}
