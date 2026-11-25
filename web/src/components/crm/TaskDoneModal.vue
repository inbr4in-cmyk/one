<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiInput, UiModal } from '@/components/ui'
import TaskForm, { type TaskDraft } from './TaskForm.vue'
import { leadTasksApi, type LeadTask } from '@/api/crm'
import { apiErr } from '@/utils/err'
import { addDays, isoDate, schoolIso, schoolNow, todayIso } from '@/utils/dates'

/** Closing a task: what came of it and the next task on the lead (a daily task comes back by itself). */
const props = defineProps<{ task: LeadTask | null }>()
const emit = defineEmits<{ close: []; done: [LeadTask, LeadTask | null] }>()
const { t } = useI18n()
const result = ref('')
const next = ref<TaskDraft>({ title: '', date: '', time: '10:00', daily: false })
const err = ref<string | null>(null)
const busy = ref(false)

watch(() => props.task, (x) => {
  if (!x) return
  result.value = ''
  err.value = null
  next.value = { title: '', date: isoDate(addDays(schoolNow(), 1)), time: '10:00', daily: false }
})

async function save() {
  const x = props.task
  if (!x) return
  busy.value = true
  err.value = null
  try {
    const n = next.value
    const r = await leadTasksApi.done(x.id, {
      result: result.value.trim() || null,
      next: !x.daily && n.title.trim() ? { title: n.title.trim(), due_at: schoolIso(n.date || todayIso(), n.time || '10:00'), daily: n.daily } : null,
    })
    emit('done', r.done, r.next)
    emit('close')
  } catch (e) {
    err.value = apiErr(e) ?? t('errors.generic')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiModal :open="task !== null" :title="t('nv.lt.doneTitle')" @update:open="(v) => !v && emit('close')">
    <form v-if="task" id="lt-done" class="stack" @submit.prevent="save">
      <p class="m0"><b>{{ task.title }}</b><span class="muted"> · {{ task.lead.full_name }}</span></p>
      <UiInput v-model="result" :label="t('nv.lt.result')" :maxlength="1000" />
      <p v-if="task.daily" class="m0 muted">{{ t('nv.lt.dailyNext') }}</p>
      <template v-else>
        <h4 class="sec-h m0">{{ t('nv.lt.next') }}</h4>
        <TaskForm v-model="next" :min="todayIso()" />
      </template>
      <p v-if="err" class="form-err m0" role="alert">{{ err }}</p>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="primary" type="submit" form="lt-done" icon="ok" :loading="busy">{{ t('nv.lt.done') }}</UiButton>
    </template>
  </UiModal>
</template>
