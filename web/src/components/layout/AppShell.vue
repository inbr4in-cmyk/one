<script setup lang="ts">
import { watch } from 'vue'
import { useRoute } from 'vue-router'
import SideBar from './SideBar.vue'
import TopBar from './TopBar.vue'
import BottomNav from './BottomNav.vue'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const route = useRoute()

// Close the mobile drawer on navigation.
watch(() => route.fullPath, () => (ui.sidebarOpen = false))

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape' && ui.sidebarOpen) ui.sidebarOpen = false
}
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
          <main :key="r.path" class="screen">
            <component :is="Component" />
          </main>
        </Transition>
      </RouterView>
    </div>
    <BottomNav />
  </div>
</template>
