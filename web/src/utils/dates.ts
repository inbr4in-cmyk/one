import { intlLocale, type Locale } from '@/i18n'

const pad = (n: number) => String(n).padStart(2, '0')

/** YYYY-MM-DD in local time (inputs of type=date, API date filters). */
export function isoDate(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** Local Date for a YYYY-MM-DD string. */
export function parseDate(s: string): Date {
  const [y, m, d] = s.split('-').map(Number)
  return new Date(y ?? 1970, (m ?? 1) - 1, d ?? 1)
}

export function addDays(d: Date, n: number): Date {
  const r = new Date(d)
  r.setDate(r.getDate() + n)
  return r
}

/** Monday 00:00 of the week that contains `d`. */
export function weekStart(d: Date): Date {
  const r = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  r.setDate(r.getDate() - ((r.getDay() + 6) % 7))
  return r
}

export function sameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
}

/** "16:00" */
export function hm(iso: string | Date, locale: Locale): string {
  return new Date(iso).toLocaleTimeString(intlLocale(locale), { hour: '2-digit', minute: '2-digit' })
}

/** "Сб, 24 окт." */
export function dayLabel(iso: string | Date, locale: Locale, opts: Intl.DateTimeFormatOptions = { weekday: 'short', day: 'numeric', month: 'short' }): string {
  return new Date(iso).toLocaleDateString(intlLocale(locale), opts)
}

/** "24.10.26" */
export function dmy(iso: string | Date, locale: Locale): string {
  return new Date(iso).toLocaleDateString(intlLocale(locale), { day: '2-digit', month: '2-digit', year: '2-digit' })
}

/** Value for <input type="datetime-local"> */
export function localInput(d: Date): string {
  return `${isoDate(d)}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** Hours since midnight, e.g. 16.5 for 16:30. */
export function hoursOf(iso: string | Date): number {
  const d = new Date(iso)
  return d.getHours() + d.getMinutes() / 60
}

/** "36 000 ₸" */
export function money(n: number | null | undefined, locale: Locale): string {
  return `${Math.round(n ?? 0).toLocaleString(intlLocale(locale)).replace(/,/g, ' ')} ₸`
}

/** Minutes → "12 мин", "3 ч 5 мин", "2 дн" using short unit labels. */
export function waitLabel(min: number, u: { m: string; h: string; d: string }): string {
  if (min < 60) return `${min} ${u.m}`
  if (min < 1440) return `${Math.floor(min / 60)} ${u.h} ${min % 60} ${u.m}`
  return `${Math.floor(min / 1440)} ${u.d}`
}

/** Age in full years from YYYY-MM-DD. */
export function ageOf(birth: string | null): number | null {
  if (!birth) return null
  const b = parseDate(birth)
  const now = new Date()
  let a = now.getFullYear() - b.getFullYear()
  if (now.getMonth() < b.getMonth() || (now.getMonth() === b.getMonth() && now.getDate() < b.getDate())) a--
  return a
}

/** "с марта 2025" style month + year. */
export function shortMonthYear(iso: string, locale: Locale): string {
  return new Date(iso).toLocaleDateString(intlLocale(locale), { month: 'long', year: 'numeric' })
}

/** Short weekday name; 0 = Monday (backend convention). */
export function weekdayShort(i: number, locale: Locale): string {
  return new Date(2024, 0, 1 + i).toLocaleDateString(intlLocale(locale), { weekday: 'short' })
}

/** "Пн/Ср/Пт 16:00–17:30" from schedule rules. */
export function ruleSummary(rules: { weekdays: number[]; start: string; end: string }[], locale: Locale): string {
  return rules.map((r) => `${r.weekdays.map((d) => weekdayShort(d, locale)).join('/')} ${r.start.slice(0, 5)}–${r.end.slice(0, 5)}`).join(', ')
}

/** "Сегодня", "Вчера" or "12 октября" for day separators in a thread. */
export function dayTitle(iso: string, locale: Locale, today: string, yesterday: string): string {
  const d = new Date(iso)
  const now = new Date()
  if (sameDay(d, now)) return today
  if (sameDay(d, addDays(now, -1))) return yesterday
  return d.toLocaleDateString(intlLocale(locale), { day: 'numeric', month: 'long', ...(d.getFullYear() !== now.getFullYear() ? { year: 'numeric' } : {}) })
}

/** Adds `day` to the first message of each calendar day. */
export function withDays<T extends { at: string }>(items: T[]): (T & { newDay: boolean })[] {
  return items.map((m, i) => ({ ...m, newDay: i === 0 || !sameDay(new Date(items[i - 1]!.at), new Date(m.at)) }))
}
