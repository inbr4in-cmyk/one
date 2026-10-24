<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter, type RouteLocationNormalizedLoaded } from 'vue-router'
import { UiAvatar, UiButton, UiEmptyState, UiIcon, UiSkeleton } from '@/components/ui'
import BrandLogo from '@/components/layout/BrandLogo.vue'
import NotificationsMenu from '@/components/layout/NotificationsMenu.vue'
import RulesGate from '@/components/compliance/RulesGate.vue'
import { useAuthStore } from '@/stores/auth'
import { useCountersStore } from '@/stores/counters'
import { usePortalStore } from '@/stores/portal'
import { startRealtime, stopRealtime } from '@/composables/useRealtime'

/** Student / parent cabinet. Mobile-first: bottom tabs on phones, a tab row on wide screens. The Flutter app follows this layout. */
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const counters = useCountersStore()
const portal = usePortalStore()

/** Pages that stay open while the child's access is paused for non-payment */
const OPEN_WHEN_BLOCKED = new Set(['portal-home', 'portal-payments', 'portal-profile', 'portal-rules', 'portal-feedback'])
const TABS = [
  { name: 'portal-home', path: '/portal', icon: 'home', key: 'home' },
  { name: 'portal-schedule', path: '/portal/schedule', icon: 'cal', key: 'schedule' },
  { name: 'portal-homework', path: '/portal/homework', icon: 'homework', key: 'homework' },
  { name: 'portal-progress', path: '/portal/progress', icon: 'progress', key: 'progress', wide: true },
  { name: 'portal-payments', path: '/portal/payments', icon: 'wallet', key: 'payments', wide: true },
  { name: 'portal-coins', path: '/portal/coins', icon: 'coin', key: 'coins', wide: true },
  { name: 'portal-chats', path: '/portal/chats', icon: 'chat', key: 'chats', counter: 'chats' },
  { name: 'portal-profile', path: '/portal/profile', icon: 'user', key: 'more' },
]
const active = computed(() => route.name as string)
const blockedHere = computed(() => portal.blocked && !OPEN_WHEN_BLOCKED.has(active.value))
const pageKey = (r: RouteLocationNormalizedLoaded) => `${r.matched[r.matched.length - 1]?.path ?? r.path}:${portal.child?.id ?? 0}`

onMounted(async () => {
  counters.start()
  startRealtime()
  await portal.load()
  const q = Number(route.query.child)
  if (q && portal.children.some((c) => c.id === q)) {
    portal.select(q)
    router.replace({ query: { ...route.query, child: undefined } })
  }
})
onBeforeUnmount(() => {
  counters.stop()
  stopRealtime()
})
// Coins and blocked status change after payments and orders: refresh the overview on navigation home
watch(() => route.name, (n) => n === 'portal-home' && portal.me && portal.load())
</script>

<template>
  <div class="portal">
    <header class="p-top">
      <RouterLink to="/portal" class="p-logo" :aria-label="t('portal.nav.home')"><BrandLogo :size="34" :tagline="false" /></RouterLink>
      <span class="sp" />
      <NotificationsMenu />
      <RouterLink to="/portal/profile" class="p-me" :aria-label="t('portal.nav.profile')">
        <UiAvatar :name="auth.user?.full_name ?? '·'" :src="auth.user?.avatar_url" size="sm" />
      </RouterLink>
    </header>

    <div v-if="portal.children.length > 1" class="p-kids" role="tablist" :aria-label="t('portal.child')">
      <button v-for="c in portal.children" :key="c.id" type="button" role="tab" class="p-kid" :aria-selected="portal.child?.id === c.id" @click="portal.select(c.id)">
        <UiAvatar :name="c.full_name" :src="c.photo_url" size="sm" /><span>{{ c.full_name.split(' ')[0] }}</span>
        <span v-if="c.blocked || c.debt" class="p-kid-dot" :title="t('portal.debt')" />
      </button>
    </div>

    <nav class="p-tabs" :aria-label="t('nav.menu')">
      <RouterLink v-for="tb in TABS" :key="tb.name" :to="tb.path" :class="{ on: active === tb.name || (tb.name === 'portal-profile' && ['portal-feedback', 'portal-rules'].includes(active)), wide: tb.wide }" :aria-current="active === tb.name ? 'page' : undefined">
        <UiIcon :name="tb.icon" :size="24" /><span class="t">{{ t(`portal.nav.${tb.key}`) }}</span>
        <span v-if="tb.counter && counters.get(tb.counter)" class="cnt">{{ counters.get(tb.counter) }}</span>
      </RouterLink>
    </nav>

    <main class="p-main" :class="{ flush: route.meta.flush }">
      <div v-if="portal.child?.blocked && !blockedHere" class="alert red p-block" role="status">
        <UiIcon name="lock" :size="18" class="ico" />
        <div class="grow"><b>{{ t('portal.blockedTitle') }}</b><span>{{ t('portal.blockedText') }}</span></div>
        <UiButton v-if="active !== 'portal-payments'" size="sm" variant="primary" to="/portal/payments">{{ t('portal.toPayments') }}</UiButton>
      </div>
      <template v-if="portal.loading && !portal.me"><div class="card card-pad"><UiSkeleton :lines="5" /></div></template>
      <UiEmptyState v-else-if="portal.failed && !portal.me" large icon="alert" :title="t('errors.generic')"><UiButton @click="portal.load()">{{ t('common.retry') }}</UiButton></UiEmptyState>
      <UiEmptyState v-else-if="portal.me && !portal.child && !['portal-profile', 'portal-rules', 'portal-feedback', 'portal-chats'].includes(active)" large icon="users" :title="t('portal.noChildren')" :text="t('portal.noChildrenText')" />
      <UiEmptyState v-else-if="blockedHere" large icon="lock" :title="t('portal.blockedTitle')" :text="t('portal.blockedText')">
        <UiButton variant="primary" to="/portal/payments">{{ t('portal.toPayments') }}</UiButton>
      </UiEmptyState>
      <RouterView v-else v-slot="{ Component, route: r }">
        <Transition name="page" mode="out-in"><div :key="pageKey(r)" class="p-page"><component :is="Component" /></div></Transition>
      </RouterView>
    </main>
    <RulesGate />
  </div>
</template>
