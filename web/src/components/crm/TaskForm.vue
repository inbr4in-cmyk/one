<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { UiCheck, UiInput } from '@/components/ui'

/** Title, day and time of a task on a lead; «Каждый день» makes it come back tomorrow after it is done. */
export interface TaskDraft { title: string; date: string; time: string; daily: boolean }
const f = defineModel<TaskDraft>({ required: true })
defineProps<{ min: string }>()
const { t } = useI18n()
</script>

<template>
  <div class="stack tf">
    <UiInput v-model="f.title" :label="t('nv.lt.what')" :placeholder="t('nv.lt.whatPh')" :maxlength="255" />
    <div class="form-2">
      <UiInput v-model="f.date" type="date" :min="min" :label="t('nv.lt.day')" />
      <UiInput v-model="f.time" type="time" :label="t('nv.lt.time')" />
    </div>
    <UiCheck v-model="f.daily" :label="t('nv.lt.daily')" />
  </div>
</template>

<style scoped>
.tf { gap: 10px }
</style>
