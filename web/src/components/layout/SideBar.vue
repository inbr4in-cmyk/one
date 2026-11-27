<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { resetKept } from '@/utils/kept'
import BrandLogo from './BrandLogo.vue'
import BranchSwitcher from './BranchSwitcher.vue'
import UiIcon from '@/components/ui/UiIcon.vue'
import { useAuthStore } from '@/stores/auth'
import { useCountersStore } from '@/stores/counters'
import { useUiStore } from '@/stores/ui'
import { SECTIONS, visibleNav, type NavItem } from '@/router/nav'

const auth = useAuthStore()
const counters = useCountersStore()
const ui = useUiStore()
const route = useRoute()
const { t } = useI18n()

const items = computed(() => visibleNav(auth.can))
type Entry = { item: NavItem } | { section: 'student' | 'money'; items: NavItem[] }
/** The menu from top to bottom: single items, and headings that fold their items («Студент», «Финансы»). */
const main = computed(() => {
  const out: Entry[] = []
  for (const i of items.value.filter((x) => x.group === 'main')) {
    const sec = i.section
    const box = sec && out.find((e): e is Extract<Entry, { section: string }> => 'section' in e && e.section === sec)
    if (box) box.items.push(i)
    else out.push(sec ? { section: sec, items: [i] } : { item: i })
  }
  return out
})
const settings = computed(() => items.value.filter((i) => i.group === 'settings'))
const activeKey = computed(() => (route.meta.parent as string | undefined) ?? (route.name as string | undefined))

// Which headings are open: remembered on this device; the one that holds the open page opens by itself.
const OPEN_KEY = 'oe.nav.open'
function saved(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(OPEN_KEY) ?? '[]')
    return Array.isArray(v) ? v.filter((x) => typeof x === 'string') : []
  } catch {
    return []
  }
}
const open = ref<Set<string>>(new Set(saved()))
function toggle(sec: string) {
  const next = new Set(open.value)
  if (!next.delete(sec)) next.add(sec)
  open.value = next
  try {
    localStorage.setItem(OPEN_KEY, JSON.stringify([...next]))
  } catch {
    /* private window: the menu just does not remember */
  }
}
const activeSection = computed(() => items.value.find((i) => i.key === activeKey.value)?.section)
watch(activeSection, (sec) => {
  if (sec && !open.value.has(sec)) open.value = new Set([...open.value, sec])
}, { immediate: true })

// Sliding red indicator next to the active item
const navEl = ref<HTMLElement | null>(null)
const ind = ref({ y: 0, visible: false, animate: false })
function placeIndicator() {
  // the open page's item, or its heading while that is folded
  const a = navEl.value?.querySelector<HTMLElement>('.sec.has:not(.open)') ?? navEl.value?.querySelector<HTMLElement>('a.on')
  if (!a || !navEl.value) {
    ind.value.visible = false
    return
  }
  ind.value.y = a.getBoundingClientRect().top - navEl.value.getBoundingClientRect().top + (a.offsetHeight - 22) / 2
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
watch(() => [activeKey.value, items.value.length, ui.locale, open.value], () => nextTick(placeIndicator))
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
      <template v-for="e in main" :key="'item' in e ? e.item.key : e.section">
        <RouterLink v-if="'item' in e" :to="e.item.path" @click="resetKept()" :class="{ on: activeKey === e.item.key }" :aria-current="activeKey === e.item.key ? 'page' : undefined">
          <UiIcon :name="e.item.icon" />{{ t(`nav.${e.item.key}`) }}
          <span v-if="counters.get(e.item.counter)" class="cnt" :class="{ soft: e.item.soft }">{{ counters.get(e.item.counter) }}</span>
        </RouterLink>
        <div v-else class="fold" :class="{ open: open.has(e.section) }">
          <button type="button" class="sec" :class="{ open: open.has(e.section), has: activeSection === e.section }" :aria-expanded="open.has(e.section)" :aria-controls="`nav-${e.section}`" :data-testid="`nav-${e.section}`" @click="toggle(e.section)">
            <UiIcon :name="SECTIONS[e.section].icon" />{{ t(`nav.sec.${e.section}`) }}<UiIcon name="down" :size="16" class="chev" />
          </button>
          <div :id="`nav-${e.section}`" class="sub" :inert="!open.has(e.section)">
            <div>
              <RouterLink v-for="it in e.items" :key="it.key" :to="it.path" @click="resetKept()" :class="{ on: activeKey === it.key }" :aria-current="activeKey === it.key ? 'page' : undefined">
                <span class="dot" aria-hidden="true" />{{ t(`nav.${it.key}`) }}
              </RouterLink>
            </div>
          </div>
        </div>
      </template>
      <template v-if="settings.length">
        <div class="sep">{{ t('nav.settings') }}</div>
        <RouterLink v-for="it in settings" :key="it.key" :to="it.path" @click="resetKept()" :class="{ on: activeKey === it.key }" :aria-current="activeKey === it.key ? 'page' : undefined">
          <UiIcon :name="it.icon" />{{ t(`nav.${it.key}`) }}
        </RouterLink>
      </template>
    </nav>
    <div class="foot">{{ t('app.footer') }}<br />{{ t('app.since') }}</div>
  </aside>
</template>
