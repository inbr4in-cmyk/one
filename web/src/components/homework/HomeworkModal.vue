<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiField, UiInput, UiModal, UiTextarea } from '@/components/ui'
import { academicsApi, type Homework } from '@/api/academics'
import { useToastStore } from '@/stores/toast'
import { addDays, isoDate } from '@/utils/dates'
import { apiErr } from '@/utils/err'

/** Create or edit a group's homework. Due date is optional; it is stored as the end of that day, local time. */
const props = defineProps<{ groupId: number; homework?: Homework | null; lessonId?: number | null; defaultTitle?: string }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ saved: [h: Homework] }>()
const { t } = useI18n()
const toast = useToastStore()

const title = ref('')
const body = ref('')
const due = ref('')
const time = ref('23:59')
const error = ref<string | null>(null)
const busy = ref(false)

const pad = (n: number) => String(n).padStart(2, '0')
watch(open, (v) => {
  if (!v) return
  const h = props.homework
  title.value = h?.title ?? props.defaultTitle ?? ''
  body.value = h?.body ?? ''
  if (h?.due_at) {
    const d = new Date(h.due_at)
    due.value = isoDate(d)
    time.value = `${pad(d.getHours())}:${pad(d.getMinutes())}`
  } else {
    due.value = h ? '' : isoDate(addDays(new Date(), 2))
    time.value = '23:59'
  }
  error.value = null
})

async function save() {
  error.value = title.value.trim().length < 2 ? t('hw.titleRequired') : null
  if (error.value) return
  busy.value = true
  const payload = {
    title: title.value.trim(),
    body: body.value.trim() || null,
    due_at: due.value ? new Date(`${due.value}T${time.value || '23:59'}:00`).toISOString() : null,
  }
  try {
    const h = props.homework
      ? await academicsApi.editHomework(props.homework.id, payload)
      : await academicsApi.addHomework(props.groupId, { ...payload, lesson_id: props.lessonId ?? null })
    toast.ok(props.homework ? t('hw.saved') : t('groups.hw.added'))
    emit('saved', h)
    open.value = false
  } catch (e) {
    error.value = apiErr(e) ?? t('errors.generic')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiModal v-model:open="open" :title="homework ? t('hw.editTitle') : t('groups.hw.new')">
    <form id="hw-form" class="stack" @submit.prevent="save">
      <UiInput v-model="title" :label="t('groups.hw.name')" :placeholder="t('attendance.hwPh')" :maxlength="255" autofocus />
      <UiTextarea v-model="body" :label="t('groups.hw.body')" :rows="4" :maxlength="8000" />
      <div class="form-2">
        <UiField :label="t('groups.hw.dueLabel')"><input v-model="due" type="date" class="inp" :aria-label="t('groups.hw.dueLabel')" /></UiField>
        <UiField :label="t('hw.time')"><input v-model="time" type="time" class="inp" :disabled="!due" :aria-label="t('hw.time')" /></UiField>
      </div>
      <p v-if="error" class="form-err" role="alert">{{ error }}</p>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton type="submit" form="hw-form" variant="navy" :loading="busy">{{ homework ? t('common.save') : t('hw.give') }}</UiButton>
    </template>
  </UiModal>
</template>
