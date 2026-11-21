<script setup lang="ts">
import { onBeforeUnmount, onMounted, watch } from 'vue'
import { useRoute, type RouteLocationNormalizedLoaded } from 'vue-router'
import SideBar from './SideBar.vue'
import TopBar from './TopBar.vue'
import BottomNav from './BottomNav.vue'
import { useUiStore } from '@/stores/ui'
import { useCountersStore } from '@/stores/counters'
import { useRefsStore } from '@/stores/refs'
import { onRealtime, startRealtime, stopRealtime } from '@/composables/useRealtime'
import { useToastStore } from '@/stores/toast'

const ui = useUiStore()
const route = useRoute()
const counters = useCountersStore()
const refs = useRefsStore()
const toast = useToastStore()
let offAlert: (() => void) | null = null

onMounted(() => {
  refs.load()
  counters.start()
  startRealtime()
  // A client's message for me, a free lead, a lead to work: shown on the screen until closed; a click opens it.
  offAlert = onRealtime('alert', (e) => {
    const link = typeof e.link === 'string' && e.link.startsWith('/') ? e.link : undefined
    if (link && route.path === link) return
    toast.show([e.title, e.body].filter(Boolean).join('. '), 'info', 0, link)
    counters.refresh()
  })
})
onBeforeUnmount(() => {
  counters.stop()
  offAlert?.()
  stopRealtime()
})

/** Same page component across param changes (e.g. /inbox → /inbox/5) keeps its state; other moves animate. */
const pageKey = (r: RouteLocationNormalizedLoaded) => r.matched[r.matched.length - 1]?.path ?? r.path

// Close the mobile drawer on navigation.
watch(() => route.fullPath, () => (ui.sidebarOpen = false))

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape' && ui.sidebarOpen) ui.sidebarOpen = false
}
import RulesGate from '@/components/compliance/RulesGate.vue'
import UserDocsGate from '@/components/compliance/UserDocsGate.vue'
</script>

<template>
  <div class="app" @keydown="onKey">
    <SideBar />
    <Transition name="fade">
      <div v-if="ui.sidebarOpen" class="scrim" aria-hidden="true" @click="ui.sidebarOpen = false" />
    </Transition>
    <div class="main">
      <TopBar />
      <RouterView v-slot="{ Component, route: r }">
        <Transition name="page" mode="out-in">
          <main :key="pageKey(r)" class="screen" :class="r.meta.flush && 'flush'">
            <component :is="Component" />
          </main>
        </Transition>
      </RouterView>
    </div>
    <BottomNav />
    <RulesGate />
    <UserDocsGate />
  </div>
</template>
