<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import UiEmptyState from '@/components/ui/UiEmptyState.vue'

const route = useRoute()
const { t } = useI18n()
const name = computed(() => (route.meta.title ? t(route.meta.title) : ''))
</script>

<template>
  <div class="ph"><div><h1>{{ name }}</h1></div></div>
  <div class="card">
    <UiEmptyState large :icon="route.meta.icon ?? 'task'" :title="t('stub.title')" :text="t('stub.text', { name })" />
  </div>
</template>
