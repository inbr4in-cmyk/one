<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import UiIcon from '@/components/ui/UiIcon.vue'
import SearchBox from './SearchBox.vue'
import NotificationsMenu from './NotificationsMenu.vue'
import UserMenu from './UserMenu.vue'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const { t } = useI18n()
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
    <SearchBox />
    <span class="sp" />
    <NotificationsMenu />
    <UserMenu />
  </header>
</template>
