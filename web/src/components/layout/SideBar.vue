<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import BrandLogo from './BrandLogo.vue'
import BranchSwitcher from './BranchSwitcher.vue'
import UiIcon from '@/components/ui/UiIcon.vue'
import { useAuthStore } from '@/stores/auth'
import { useCountersStore } from '@/stores/counters'
import { useUiStore } from '@/stores/ui'
import { visibleNav } from '@/router/nav'

const auth = useAuthStore()
const counters = useCountersStore()
const ui = useUiStore()
const route = useRoute()
const { t } = useI18n()

const items = computed(() => visibleNav(auth.can))
const main = computed(() => items.value.filter((i) => i.group === 'main'))
const settings = computed(() => items.value.filter((i) => i.group === 'settings'))
const activeKey = computed(() => (route.meta.parent as string | undefined) ?? (route.name as string | undefined))

// Sliding red indicator next to the active item
const navEl = ref<HTMLElement | null>(null)
const ind = ref({ y: 0, visible: false, animate: false })
function placeIndicator() {
  const a = navEl.value?.querySelector<HTMLElement>('a.on')
  if (!a) {
    ind.value.visible = false
    return
  }
  ind.value.y = a.offsetTop + (a.offsetHeight - 22) / 2
  ind.value.visible = true
  // Enable the slide only after the first placement, so it doesn't fly in from the top.
  requestAnimationFrame(() => (ind.value.animate = true))
}
let ro: ResizeObserver | null = null
onMounted(() => {
  placeIndicator()
  ro = new ResizeObserver(placeIndicator)
  if (navEl.value) ro.observe(navEl.value)
})
onBeforeUnmount(() => ro?.disconnect())
watch(() => [activeKey.value, items.value.length, ui.locale], () => nextTick(placeIndicator))
</script>

<template>
  <aside id="sidebar" class="side" :class="{ open: ui.sidebarOpen }" :aria-label="t('nav.menu')">
    <RouterLink to="/" class="home-link"><BrandLogo /></RouterLink>
    <BranchSwitcher v-if="auth.isStaff" />
    <div class="lbl">{{ t('nav.menu') }}</div>
    <nav ref="navEl" class="nav">
      <span
        class="ind"
        aria-hidden="true"
        :style="{ transform: `translateY(${ind.y}px)`, opacity: ind.visible ? 1 : 0, transition: ind.animate ? undefined : 'none' }"
      />
      <RouterLink v-for="it in main" :key="it.key" :to="it.path" :class="{ on: activeKey === it.key }" :aria-current="activeKey === it.key ? 'page' : undefined">
        <UiIcon :name="it.icon" />{{ t(`nav.${it.key}`) }}
        <span v-if="counters.get(it.counter)" class="cnt" :class="{ soft: it.soft }">{{ counters.get(it.counter) }}</span>
      </RouterLink>
      <template v-if="settings.length">
        <div class="sep">{{ t('nav.settings') }}</div>
        <RouterLink v-for="it in settings" :key="it.key" :to="it.path" :class="{ on: activeKey === it.key }" :aria-current="activeKey === it.key ? 'page' : undefined">
          <UiIcon :name="it.icon" />{{ t(`nav.${it.key}`) }}
        </RouterLink>
      </template>
    </nav>
    <div class="foot">{{ t('app.footer') }}<br />{{ t('app.since') }}</div>
  </aside>
</template>
