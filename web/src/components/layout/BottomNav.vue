<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import UiIcon from '@/components/ui/UiIcon.vue'
import { useAuthStore } from '@/stores/auth'
import { useCountersStore } from '@/stores/counters'
import { useUiStore } from '@/stores/ui'
import { visibleNav } from '@/router/nav'

const auth = useAuthStore()
const counters = useCountersStore()
const ui = useUiStore()
const { t } = useI18n()
const items = computed(() => visibleNav(auth.can).filter((i) => i.group === 'main').slice(0, 4))
</script>

<template>
  <nav class="bnav" :aria-label="t('nav.menu')">
    <RouterLink v-for="it in items" :key="it.key" :to="it.path" active-class="on">
      <UiIcon :name="it.icon" :size="24" /><span class="t">{{ t(`nav.${it.key}`) }}</span>
      <span v-if="counters.get(it.counter) && !it.soft" class="cnt">{{ counters.get(it.counter) }}</span>
    </RouterLink>
    <button type="button" aria-controls="sidebar" :aria-expanded="ui.sidebarOpen" @click="ui.sidebarOpen = true">
      <UiIcon name="menu" :size="24" /><span class="t">{{ t('common.more') }}</span>
    </button>
  </nav>
</template>
