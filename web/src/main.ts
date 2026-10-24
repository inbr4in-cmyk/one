import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { router } from './router'
import { i18n, t } from './i18n'
import { setAuthLostHandler, setErrorHandler } from './api/http'
import { useAuthStore } from './stores/auth'
import { useToastStore } from './stores/toast'
import { useUiStore } from './stores/ui'
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
setAuthLostHandler(() => {
  useAuthStore().clear()
  const current = router.currentRoute.value
  if (!current.meta.public) {
    router.replace({ name: 'login', query: current.fullPath !== '/' ? { redirect: current.fullPath } : {} })
  }
})

app.use(router)
router.isReady().then(() => app.mount('#app'))
