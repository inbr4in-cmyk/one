<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { NAV } from '@/router/nav'
import UiIcon from '@/components/ui/UiIcon.vue'
import SearchBox from './SearchBox.vue'
import NotificationsMenu from './NotificationsMenu.vue'
import UserMenu from './UserMenu.vue'
import CheckinMenu from './CheckinMenu.vue'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
/** Detail pages: back to the list one came from, its filters as they were. */
function back() {
  if (window.history.state?.back) router.back()
  else router.push(NAV.find((n) => n.key === route.meta.parent)?.path ?? '/')
}
</script>

<template>
  <header class="top">
    <button
      type="button"
      class="iconbtn burger"
      :aria-label="t('top.openMenu')"
      aria-controls="sidebar"
      :aria-expanded="ui.sidebarOpen"
      @click="ui.sidebarOpen = true"
    >
      <UiIcon name="menu" />
    </button>
    <button v-if="route.meta.parent" type="button" class="backbtn" @click="back"><UiIcon name="arrow" :size="18" class="flip-ico" /><span>{{ t('common.back') }}</span></button>
    <SearchBox />
    <span class="sp" />
    <CheckinMenu />
    <NotificationsMenu />
    <UserMenu />
  </header>
</template>
