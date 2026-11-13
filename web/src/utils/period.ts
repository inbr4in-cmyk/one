import { intlLocale, type Locale } from '@/i18n'
import { schoolNow } from './dates'

/** Payroll / finance periods are months written "YYYY-MM". */
export function periodOf(d: Date = schoolNow()): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

export function shiftPeriod(p: string, n: number): string {
  const [y, m] = p.split('-').map(Number) as [number, number]
  return periodOf(new Date(y, m - 1 + n, 1))
}

/** "октябрь 2026" */
export function periodLabel(p: string, locale: Locale, opts: Intl.DateTimeFormatOptions = { month: 'long', year: 'numeric' }): string {
  const [y, m] = p.split('-').map(Number) as [number, number]
  const s = new Date(y, m - 1, 1).toLocaleDateString(intlLocale(locale), opts)
  return s.charAt(0).toUpperCase() + s.slice(1)
}

/** Compact money for tiles and chart axes: 14 860 000 → "14,86 млн". */
export function compactMoney(n: number, locale: Locale): { v: string; unit: 'mln' | 'k' | '' } {
  const tag = intlLocale(locale)
  if (Math.abs(n) >= 1_000_000) return { v: (n / 1_000_000).toLocaleString(tag, { maximumFractionDigits: 2 }), unit: 'mln' }
  if (Math.abs(n) >= 10_000) return { v: (n / 1000).toLocaleString(tag, { maximumFractionDigits: 1 }), unit: 'k' }
  return { v: n.toLocaleString(tag), unit: '' }
}

export function num(n: number | null | undefined, locale: Locale, digits = 0): string {
  return n === null || n === undefined ? '—' : n.toLocaleString(intlLocale(locale), { maximumFractionDigits: digits })
}
