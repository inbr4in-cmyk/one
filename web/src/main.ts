import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { router } from './router'
import { i18n, t } from './i18n'
import { setAuthLostHandler, setErrorHandler, setMfaRequiredHandler } from './api/http'
import { useAuthStore } from './stores/auth'
import { useToastStore } from './stores/toast'
import { useUiStore } from './stores/ui'
import { setRealtimeSessionLost } from './composables/useRealtime'
import './styles/index.css'

const app = createApp(App)
app.use(createPinia())
app.use(i18n)

useUiStore() // applies saved theme and language

const toast = useToastStore()
setErrorHandler((err) => {
  const fallback = err.status === 0 ? t('errors.network') : err.status >= 500 ? t('errors.server') : t('errors.generic')
  toast.error(err.detail || fallback)
})
const onAuthLost = () => {
  useAuthStore().clear()
  const current = router.currentRoute.value
  if (!current.meta.public) {
    router.replace({ name: 'login', query: current.fullPath !== '/' ? { redirect: current.fullPath } : {} })
  }
}
setAuthLostHandler(onAuthLost)
setRealtimeSessionLost(onAuthLost)

// The server requires 2FA for staff: whatever screen asked, the answer is the setup flow.
let mfaRedirecting = false
setMfaRequiredHandler(async () => {
  if (mfaRedirecting || router.currentRoute.value.name === 'setup-2fa') return
  mfaRedirecting = true
  const auth = useAuthStore()
  await auth.fetchMe()
  if (auth.user) auth.user.mfa_setup_required = true
  await router.replace({ name: 'setup-2fa' }).finally(() => (mfaRedirecting = false))
})

app.use(router)
router.isReady().then(() => app.mount('#app'))
