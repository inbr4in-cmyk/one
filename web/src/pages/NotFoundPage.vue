<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import UiButton from '@/components/ui/UiButton.vue'
import UiEmptyState from '@/components/ui/UiEmptyState.vue'

const { t } = useI18n()
</script>

<template>
  <div class="card">
    <UiEmptyState large icon="flag" :title="t('notFound.title')" :text="t('notFound.text')">
      <UiButton variant="navy" to="/" icon-end="arrow">{{ t('common.toHome') }}</UiButton>
    </UiEmptyState>
  </div>
</template>
