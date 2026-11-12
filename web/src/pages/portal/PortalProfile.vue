<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { UiAvatar, UiButton, UiCard, UiIcon, UiSegmented } from '@/components/ui'
import ThemePicker from '@/components/layout/ThemePicker.vue'
import { useAuthStore } from '@/stores/auth'
import { usePortalStore } from '@/stores/portal'
import { useUiStore } from '@/stores/ui'
import { formatPhone } from '@/utils/phone'

/** "More": profile, the pages that don't fit the bottom bar, theme / language, sign out. */
const { t } = useI18n()
const auth = useAuthStore()
const portal = usePortalStore()
const ui = useUiStore()
const router = useRouter()
async function logout() {
  await auth.logout()
  router.replace({ name: 'login' })
}
const langs = computed(() => [{ value: 'ru' as const, label: t('lang.ru') }, { value: 'kk' as const, label: t('lang.kk') }])
const links = computed(() => [
  { to: '/portal/progress', icon: 'progress', label: t('portal.nav.progress') },
  { to: '/portal/payments', icon: 'wallet', label: t('portal.nav.payments') },
  { to: '/portal/coins', icon: 'coin', label: t('portal.nav.coins') },
  { to: '/portal/feedback', icon: 'flag', label: t('nav.feedback') },
  { to: '/portal/rules', icon: 'file', label: t('nav.rules') },
])
</script>

<template>
  <UiCard>
    <div class="who2" style="display: flex">
      <UiAvatar :name="auth.user?.full_name ?? '·'" :src="auth.user?.avatar_url" size="lg" />
      <div>
        <h2 style="margin: 0; font-family: var(--font-display); font-size: 18px">{{ auth.user?.full_name }}</h2>
        <span class="muted">{{ portal.isParent ? t('roles.parent') : t('roles.student') }}<template v-if="auth.user?.phone"> · {{ formatPhone(auth.user.phone) }}</template></span>
      </div>
    </div>
  </UiCard>
  <UiCard style="margin-top: 14px" flush>
    <div class="card-b" style="padding-top: 4px; padding-bottom: 4px">
      <RouterLink v-for="l in links" :key="l.to" :to="l.to" class="list-row">
        <UiIcon :name="l.icon" :size="20" class="muted" /><div class="grow"><b>{{ l.label }}</b></div><UiIcon name="arrow" :size="16" class="muted" />
      </RouterLink>
    </div>
  </UiCard>
  <UiCard style="margin-top: 14px" :title="t('portal.appearance')">
    <div class="set-row wrap"><div class="grow"><b>{{ t('user.theme') }}</b></div></div>
    <ThemePicker style="padding: 4px 0 12px" />
    <div class="set-row"><div class="grow"><b>{{ t('user.language') }}</b></div><UiSegmented v-model="ui.locale" :options="langs" :label="t('user.language')" size="sm" /></div>
  </UiCard>
  <div style="margin-top: 16px"><UiButton icon="logout" block @click="logout">{{ t('user.logout') }}</UiButton></div>
</template>
