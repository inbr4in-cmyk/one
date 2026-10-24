import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { LOCALES, setLocale, type Locale } from '@/i18n'
import { readPref, writePref } from '@/utils/storage'

export type ThemePref = 'light' | 'dark' | 'system'

const THEME_KEY = 'oe-theme'
const LOCALE_KEY = 'oe-locale'

function initialTheme(): ThemePref {
  const v = readPref(THEME_KEY)
  return v === 'light' || v === 'dark' ? v : 'system'
}

function initialLocale(): Locale {
  const v = readPref(LOCALE_KEY)
  return LOCALES.includes(v as Locale) ? (v as Locale) : 'ru'
}

export const useUiStore = defineStore('ui', () => {
  const theme = ref<ThemePref>(initialTheme())
  const locale = ref<Locale>(initialLocale())
  const sidebarOpen = ref(false)

  function applyTheme(t: ThemePref) {
    const root = document.documentElement
    if (t === 'system') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', t)
  }

  watch(theme, (t) => {
    applyTheme(t)
    writePref(THEME_KEY, t === 'system' ? null : t)
  }, { immediate: true })

  watch(locale, (l) => {
    setLocale(l)
    writePref(LOCALE_KEY, l)
  }, { immediate: true })

  return { theme, locale, sidebarOpen }
})
