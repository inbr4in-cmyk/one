<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import UiSegmented from '@/components/ui/UiSegmented.vue'
import { useUiStore, type ThemePref } from '@/stores/ui'
import type { Locale } from '@/i18n'

const ui = useUiStore()
const { t } = useI18n()
const themes = computed<{ value: ThemePref; label: string; icon: string; iconOnly: boolean }[]>(() => [
  { value: 'light', label: t('theme.light'), icon: 'sun', iconOnly: true },
  { value: 'dark', label: t('theme.dark'), icon: 'moon', iconOnly: true },
  { value: 'system', label: t('theme.system'), icon: 'laptop', iconOnly: true },
])
const langs = computed<{ value: Locale; label: string }[]>(() => [
  { value: 'ru', label: t('lang.ru') },
  { value: 'kk', label: t('lang.kk') },
])
</script>

<template>
  <UiSegmented v-model="ui.locale" :options="langs" :label="t('user.language')" size="sm" />
  <UiSegmented v-model="ui.theme" :options="themes" :label="t('user.theme')" size="sm" />
</template>
