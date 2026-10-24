import { intlLocale, t, type Locale } from '@/i18n'

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  return ((parts[0]?.[0] ?? '') + (parts[1]?.[0] ?? '')).toUpperCase() || '·'
}

/** Stable avatar color class c1..c8 for an id or a name. */
export function avatarColor(seed: number | string): number {
  const n = typeof seed === 'number' ? seed : [...seed].reduce((a, ch) => (a * 31 + ch.charCodeAt(0)) >>> 0, 7)
  return (Math.abs(n) % 8) + 1
}

/** "сейчас", "12 мин назад", "вчера, 18:40", "12 окт., 09:15" */
export function relativeTime(iso: string, locale: Locale, now = new Date()): string {
  const d = new Date(iso)
  const tag = intlLocale(locale)
  const diffMin = Math.round((now.getTime() - d.getTime()) / 60000)
  if (diffMin < 1) return t('time.now')
  const rtf = new Intl.RelativeTimeFormat(tag, { numeric: 'auto', style: 'short' })
  if (diffMin < 60) return rtf.format(-diffMin, 'minute')
  const time = d.toLocaleTimeString(tag, { hour: '2-digit', minute: '2-digit' })
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  if (d.getTime() >= startOfToday) return rtf.format(-Math.round(diffMin / 60), 'hour')
  if (d.getTime() >= startOfToday - 86400000) return t('time.yesterday', { time })
  return d.toLocaleString(tag, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export function shortDate(iso: string, locale: Locale): string {
  return new Date(iso).toLocaleDateString(intlLocale(locale), { day: 'numeric', month: 'short', year: 'numeric' })
}

export interface DeviceInfo {
  label: string
  mobile: boolean
}

/** Human device label from a User-Agent: "Chrome · Windows", "One English · iPhone". */
export function describeUserAgent(ua: string | null): DeviceInfo | null {
  if (!ua) return null
  const os =
    /iPhone/.test(ua) ? 'iPhone'
    : /iPad/.test(ua) ? 'iPad'
    : /Android/.test(ua) ? 'Android'
    : /Windows/.test(ua) ? 'Windows'
    : /Mac OS X|Macintosh/.test(ua) ? 'macOS'
    : /Linux/.test(ua) ? 'Linux'
    : null
  const app =
    /OneEnglish|okhttp|Dart|Expo/i.test(ua) ? 'One English'
    : /Edg\//.test(ua) ? 'Edge'
    : /OPR\/|Opera/.test(ua) ? 'Opera'
    : /YaBrowser/.test(ua) ? 'Яндекс Браузер'
    : /Firefox\//.test(ua) ? 'Firefox'
    : /Chrome\/|CriOS/.test(ua) ? 'Chrome'
    : /Safari\//.test(ua) ? 'Safari'
    : null
  const label = [app, os].filter(Boolean).join(' · ')
  return label ? { label, mobile: /Mobile|iPhone|Android|iPad/.test(ua) } : null
}
