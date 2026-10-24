<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import UiIcon from '@/components/ui/UiIcon.vue'
import UiKbd from '@/components/ui/UiKbd.vue'
import UiModal from '@/components/ui/UiModal.vue'
import UiInput from '@/components/ui/UiInput.vue'
import UiEmptyState from '@/components/ui/UiEmptyState.vue'
import { useHotkey } from '@/composables/useHotkey'
import { useMediaQuery } from '@/composables/useMediaQuery'

const { t } = useI18n()
const query = ref('')
const input = ref<HTMLInputElement | null>(null)
const modalOpen = ref(false)
const narrow = useMediaQuery('(max-width: 760px)')
const isMac = /Mac|iPhone|iPad/.test(navigator.platform)

function focusSearch() {
  if (narrow.value) modalOpen.value = true
  else {
    input.value?.focus()
    input.value?.select()
  }
}
useHotkey('k', focusSearch)
</script>

<template>
  <label class="search">
    <UiIcon name="search" :size="18" />
    <input ref="input" v-model="query" type="search" :placeholder="t('top.searchPlaceholder')" :aria-label="t('top.search')" />
    <UiKbd>{{ isMac ? '⌘' : 'Ctrl' }} K</UiKbd>
  </label>
  <button type="button" class="iconbtn search-btn" :aria-label="t('top.search')" @click="modalOpen = true">
    <UiIcon name="search" />
  </button>
  <UiModal v-model:open="modalOpen" :title="t('top.search')">
    <div class="stack">
      <UiInput v-model="query" type="search" icon="search" :placeholder="t('top.searchPlaceholder')" autofocus />
      <UiEmptyState icon="search" :title="t('top.search')" :text="t('top.searchSoon')" />
    </div>
  </UiModal>
</template>
