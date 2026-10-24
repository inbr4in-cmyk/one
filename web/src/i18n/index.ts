import { createI18n } from 'vue-i18n'
import ru, { type Messages } from './ru'
import kk from './kk'

export type Locale = 'ru' | 'kk'
export const LOCALES: Locale[] = ['ru', 'kk']

export const i18n = createI18n<[Messages], Locale, false>({
  legacy: false,
  locale: 'ru',
  fallbackLocale: 'ru',
  messages: { ru, kk },
  missingWarn: import.meta.env.DEV,
  fallbackWarn: false,
})

/** Intl locale tag for dates and numbers. */
export function intlLocale(locale: Locale): string {
  return locale === 'kk' ? 'kk-KZ' : 'ru-RU'
}

export function setLocale(locale: Locale): void {
  i18n.global.locale.value = locale
  document.documentElement.lang = locale
}

export const t = i18n.global.t
