import { http, qs } from './http'
import type { Page } from './org'

export type PaymentMethod = 'cash' | 'card' | 'kaspi' | 'transfer' | 'online'
export const PAYMENT_METHODS: PaymentMethod[] = ['kaspi', 'cash', 'card', 'transfer', 'online']

export interface PaymentIn {
  student_id: number
  lessons: number
  /** any sum paid (partial payment); whole lessons are bought, the rest goes to the money balance */
  amount?: number | null
  method: PaymentMethod
  discount?: number
  promo_code?: string | null
  note?: string | null
  level_id?: number | null
  /** selling a subscription (абонемент): price and lessons come from the package */
  package_id?: number | null
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
  package_id?: number | null
  valid_to?: string | null
  student_name: string | null
  /** The student's current balance, so a refund never defaults to more than is left */
  student_lessons_left?: number | null
}

export const paymentsApi = {
  quote: (body: PaymentIn) => http.post<Quote>('/payments/quote', body),
  /** `key`: Idempotency-Key, one per payment form, so a retried or double submit records one payment (QA C-1). */
  create: (body: PaymentIn, key: string) => http.post<Payment>('/payments', body, { headers: { 'Idempotency-Key': key } }),
  edit: (id: number, body: { method?: PaymentMethod; note?: string | null; paid_on?: string }) => http.patch<Payment>(`/payments/${id}`, body),
  refundable: (id: number) => http.get<{ lessons_max: number; amount_max: number; amount_left: number }>(`/payments/${id}/refundable`, { silent: true }),
  list: (p: { student_id?: number; branch_id?: number | null; date_from?: string; date_to?: string; limit?: number; offset?: number }) =>
    http.get<Page<Payment>>(`/payments${qs(p)}`),
  refund: (id: number, body: { lessons: number; amount: number; reason: string }) =>
    http.post<{ refund_id: number; bonuses_reversed: number }>(`/payments/${id}/refund`, body, { silent: true }),
}

/** Абонемент: N months for a fixed price; selling it adds `lessons` to the student's balance. */
export interface SubscriptionPackage {
  id: number
  name: string
  months: number
  price: number
  lessons: number
}
export type PackageIn = Omit<SubscriptionPackage, 'id'>

export const packagesApi = {
  list: () => http.get<SubscriptionPackage[]>('/packages'),
  create: (body: PackageIn) => http.post<SubscriptionPackage>('/packages', body),
  update: (id: number, body: PackageIn) => http.patch<SubscriptionPackage>(`/packages/${id}`, body),
  archive: (id: number) => http.post<void>(`/packages/${id}/archive`, {}),
}
