import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { LOCALES, setLocale, type Locale } from '@/i18n'
import { readPref, writePref } from '@/utils/storage'
import { useAuthStore } from './auth'

/**
 * Color themes. `auto` follows the system (brand light or dark); the rest are set on <html data-theme>.
 * Token sets live in styles/tokens.css. `swatch` colors are a static preview for the picker.
 */
export const THEMES = [
  { id: 'auto', dark: null, swatch: { paper: '#FAF6F3', side: '#01225F', alt: '#0A1630', accent: '#0A1630', cta: '#BB1027' } },
  { id: 'light', dark: false, swatch: { paper: '#FAF6F3', side: '#01225F', alt: '#FFFFFF', accent: '#01225F', cta: '#BB1027' } },
  { id: 'dark', dark: true, swatch: { paper: '#0A1630', side: '#07102A', alt: '#111F3D', accent: '#3A63B8', cta: '#D42A41' } },
  { id: 'ocean', dark: false, swatch: { paper: '#F2F7F7', side: '#0A4652', alt: '#FFFFFF', accent: '#12707F', cta: '#BB1027' } },
  { id: 'graphite', dark: true, swatch: { paper: '#15171B', side: '#0F1114', alt: '#1E2126', accent: '#6B7587', cta: '#D42A41' } },
  { id: 'sand', dark: false, swatch: { paper: '#F6F0E6', side: '#3A2C21', alt: '#FFFDF9', accent: '#6B5440', cta: '#BB1027' } },
] as const

export type ThemePref = (typeof THEMES)[number]['id']

/** The device-wide choice (login screen, first paint); index.html reads the same key. */
const THEME_KEY = 'oe-theme'
/** Each signed-in user keeps their own choice on this device. */
const userKey = (id: number) => `oe-theme:u${id}`
const LOCALE_KEY = 'oe-locale'

function parseTheme(v: string | null): ThemePref | null {
  if (v === 'system') return 'auto' // value saved before themes were added
  return THEMES.some((t) => t.id === v) ? (v as ThemePref) : null
}

function initialLocale(): Locale {
  const v = readPref(LOCALE_KEY)
  return LOCALES.includes(v as Locale) ? (v as Locale) : 'ru'
}

/** Status bar color on phones: the theme's sidebar. */
function applyMetaColor(t: ThemePref) {
  const meta = document.querySelector('meta[name="theme-color"]')
  if (!meta) return
  const theme = THEMES.find((x) => x.id === t)
  const dark = t === 'auto' && window.matchMedia?.('(prefers-color-scheme: dark)').matches
  meta.setAttribute('content', dark ? '#07102A' : (theme?.swatch.side ?? '#01225F'))
}

export const useUiStore = defineStore('ui', () => {
  const theme = ref<ThemePref>(parseTheme(readPref(THEME_KEY)) ?? 'auto')
  const locale = ref<Locale>(initialLocale())
  const sidebarOpen = ref(false)
  const auth = useAuthStore()

  function applyTheme(t: ThemePref) {
    const root = document.documentElement
    if (t === 'auto') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', t)
    applyMetaColor(t)
  }

  watch(theme, (t) => {
    applyTheme(t)
    writePref(THEME_KEY, t === 'auto' ? null : t)
    const uid = auth.user?.id
    if (uid) writePref(userKey(uid), t)
  }, { immediate: true })

  // On sign-in, switch to that user's own theme if they picked one on this device.
  watch(() => auth.user?.id, (uid) => {
    if (!uid) return
    const own = parseTheme(readPref(userKey(uid)))
    if (own && own !== theme.value) theme.value = own
  }, { immediate: true })

  watch(locale, (l) => {
    setLocale(l)
    writePref(LOCALE_KEY, l)
  }, { immediate: true })

  return { theme, locale, sidebarOpen }
})
