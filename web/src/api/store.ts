import { http, qs } from './http'
import type { PaymentMethod } from './payments'

export interface StockCell {
  qty: number
  min_qty: number
  low: boolean
}

export interface Book {
  id: number
  title: string
  level_id: number | null
  sale_price: number
  /** Only for users with books.stock */
  purchase_price?: number
  photo_url: string | null
  /** branch_id → stock */
  stock: Record<string, StockCell>
}

export interface BookIn {
  title: string
  level_id: number | null
  sale_price: number
  purchase_price: number
  photo_url?: string | null
}

export interface BookTransfer {
  id: number
  at: string
  from_branch_id: number
  to_branch_id: number
  book_id: number
  qty: number
}

export interface BooksReport {
  period: string
  books: { book_id: number; title: string; in?: number; sale?: number; writeoff?: number; transfer_out?: number; transfer_in?: number; revenue?: number; profit?: number }[]
  students_without_book: { student_id: number; full_name: string; book: string }[]
  totals: { revenue: number; profit: number }
}

export interface StudentBooks {
  items: { at: string; book_id: number; title: string; qty: number; price: number }[]
  needed: { id: number; title: string; price: number }[]
}

export interface CoinEntry {
  at: string
  kind: string
  delta: number
  reason: string | null
}

export interface LeaderRow {
  student_id: number | null
  name: string
  branch_id: number
  coins: number
}

export interface ShopItem {
  id: number
  name: string
  photo_url: string | null
  icon: string | null
  price_coins: number
  stock: number
  branch_id: number | null
  /** Only for users with shop.edit */
  cost?: number
}

export interface ShopItemIn {
  name: string
  icon?: string | null
  price_coins: number
  stock: number
  cost: number
  branch_id: number | null
}

export type OrderStatus = 'placed' | 'ready' | 'issued' | 'cancelled'

export interface ShopOrder {
  id: number
  student_id: number
  student: string
  item: string
  coins: number
  status: OrderStatus
  branch_id: number
  created_at: string
  issued_at: string | null
}

export const booksApi = {
  list: (branch_id?: number | null) => http.get<Book[]>(`/books${qs({ branch_id })}`),
  create: (body: BookIn) => http.post<Book>('/books', body, { silent: true }),
  update: (id: number, body: BookIn) => http.patch<Book>(`/books/${id}`, body, { silent: true }),
  receive: (body: { branch_id: number; book_id: number; qty: number; unit_price: number; supplier?: string | null }) =>
    http.post<{ id: number; qty: number }>('/books/receive', body, { silent: true }),
  transfer: (body: { from_branch_id: number; to_branch_id: number; book_id: number; qty: number }) =>
    http.post<{ id: number }>('/books/transfer', body, { silent: true }),
  transfers: () => http.get<BookTransfer[]>('/books/transfers'),
  confirm: (id: number) => http.post<{ qty: number }>(`/books/transfers/${id}/confirm`),
  writeoff: (body: { branch_id: number; book_id: number; qty: number; reason: string }) =>
    http.post<{ qty: number }>('/books/writeoff', body, { silent: true }),
  sell: (body: { student_id: number; book_id: number; method: PaymentMethod; qty: number }) =>
    http.post<{ payment_id: number; amount: number; left_in_stock: number }>('/books/sell', body, { silent: true }),
  ofStudent: (id: number) => http.get<StudentBooks>(`/students/${id}/books`, { silent: true }),
  report: (p: { period: string; branch_id?: number | null }) => http.get<BooksReport>(`/books/report${qs(p)}`),
}

export const coinsApi = {
  award: (body: { student_id: number; amount: number; reason: string }) =>
    http.post<{ balance: number; limit_left: number }>('/coins/award', body, { silent: true }),
  writeoff: (body: { student_id: number; amount: number; reason: string }) =>
    http.post<{ balance: number }>('/coins/writeoff', body, { silent: true }),
  ofStudent: (id: number) => http.get<{ balance: number; items: CoinEntry[] }>(`/students/${id}/coins`, { silent: true }),
  top: (p: { group_id?: number | null; branch_id?: number | null; period?: string | null; limit?: number } = {}) => http.get<LeaderRow[]>(`/coins/top${qs(p)}`),
  /** My manual-award limit this month */
  limit: () => http.get<{ limit: number; used: number; left: number }>('/coins/limit', { silent: true }),
}

export const shopApi = {
  items: (branch_id?: number | null) => http.get<ShopItem[]>(`/shop/items${qs({ branch_id })}`),
  create: (body: ShopItemIn) => http.post<{ id: number }>('/shop/items', body, { silent: true }),
  update: (id: number, body: ShopItemIn) => http.patch<{ id: number }>(`/shop/items/${id}`, body, { silent: true }),
  orders: (p: { status?: OrderStatus | ''; student_id?: number } = {}) => http.get<ShopOrder[]>(`/shop/orders${qs(p)}`),
  order: (student_id: number, item_id: number) => http.post<{ id: number; status: OrderStatus; balance: number }>('/shop/orders', { student_id, item_id }, { silent: true }),
  archive: (id: number) => http.post<void>(`/shop/items/${id}/archive`),
  setStatus: (id: number, status: 'ready' | 'issued' | 'cancelled') => http.post<{ id: number; status: OrderStatus }>(`/shop/orders/${id}/status`, { status }),
}
