<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import UiIcon from './UiIcon.vue'
import { periodLabel, periodOf, shiftPeriod } from '@/utils/period'
import type { Locale } from '@/i18n'

/** Month stepper for "YYYY-MM" periods; never goes past `max` (default: this month). */
const props = defineProps<{ max?: string }>()
const model = defineModel<string>({ required: true })
const { t, locale } = useI18n()
const top = computed(() => props.max ?? periodOf())
const label = computed(() => periodLabel(model.value, locale.value as Locale))
</script>

<template>
  <div class="period" role="group" :aria-label="t('period.label')">
    <button type="button" class="tgl" :aria-label="t('period.prev')" @click="model = shiftPeriod(model, -1)"><UiIcon name="arrow" :size="16" class="flip-ico" /></button>
    <span class="period-v num" aria-live="polite">{{ label }}</span>
    <button type="button" class="tgl" :aria-label="t('period.next')" :disabled="model >= top" @click="model = shiftPeriod(model, 1)"><UiIcon name="arrow" :size="16" /></button>
  </div>
</template>
