<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiInput, UiModal, UiTextarea } from '@/components/ui'
import { studentsApi, type Student } from '@/api/students'
import { ApiError } from '@/api/http'
import { useToastStore } from '@/stores/toast'
import { addDays, isoDate, parseDate, schoolNow } from '@/utils/dates'

const props = defineProps<{ student: Student }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ done: [Student] }>()
const { t } = useI18n()
const toast = useToastStore()
const form = reactive({ from: '', to: '', reason: '' })
const error = ref<string | null>(null)
const busy = ref(false)

const days = computed(() => {
  if (!form.from || !form.to) return 0
  return Math.round((parseDate(form.to).getTime() - parseDate(form.from).getTime()) / 86400000)
})

watch(open, (v) => {
  if (!v) return
  const today = schoolNow()
  Object.assign(form, { from: isoDate(today), to: isoDate(addDays(today, 14)), reason: '' })
  error.value = null
})

async function submit() {
  error.value = null
  if (days.value <= 0) {
    error.value = t('students.freeze.badRange')
    return
  }
  busy.value = true
  try {
    const s = await studentsApi.freeze(props.student.id, form.from, form.to, form.reason.trim() || null)
    toast.ok(t('students.freeze.done'))
    emit('done', s)
    open.value = false
  } catch (e) {
    if (e instanceof ApiError) error.value = e.detail
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiModal v-model:open="open" :title="t('students.freeze.title')">
    <form id="fr-form" class="stack" @submit.prevent="submit">
      <p class="muted m0">{{ t('students.freeze.text') }}</p>
      <div class="form-2">
        <UiInput v-model="form.from" type="date" :label="t('students.freeze.from')" />
        <UiInput v-model="form.to" type="date" :label="t('students.freeze.to')" :min="form.from" :hint="days > 0 ? t('students.freeze.days', { n: days }) : undefined" />
      </div>
      <UiTextarea v-model="form.reason" :label="t('common.reason')" :rows="2" />
      <p v-if="error" class="form-err m0" role="alert">{{ error }}</p>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="navy" type="submit" form="fr-form" :loading="busy">{{ t('students.freeze.confirm') }}</UiButton>
    </template>
  </UiModal>
</template>
