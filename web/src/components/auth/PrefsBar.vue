<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import UiSegmented from '@/components/ui/UiSegmented.vue'
import ThemePicker from '@/components/layout/ThemePicker.vue'
import { useUiStore } from '@/stores/ui'
import type { Locale } from '@/i18n'

const ui = useUiStore()
const { t } = useI18n()
const langs = computed<{ value: Locale; label: string }[]>(() => [
  { value: 'ru', label: t('lang.ru') },
  { value: 'kk', label: t('lang.kk') },
])
</script>

<template>
  <UiSegmented v-model="ui.locale" :options="langs" :label="t('user.language')" size="sm" />
  <ThemePicker compact />
</template>
