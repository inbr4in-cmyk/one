<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiField, UiIcon, UiInput, UiModal, UiSelect } from '@/components/ui'
import { academicsApi, type Group } from '@/api/academics'
import type { Room } from '@/api/org'
import { ApiError } from '@/api/http'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import type { TeacherOption } from '@/composables/useTeachers'
import { isoDate } from '@/utils/dates'

/** One-off lesson for a group (make-up, extra). The server refuses room/teacher conflicts with 409. */
const props = defineProps<{ groups: Group[]; teachers: TeacherOption[]; date?: string | null; roomId?: number | null }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ created: [] }>()
const { t } = useI18n()
const refs = useRefsStore()
const toast = useToastStore()
const form = reactive({ group_id: 0, teacher_id: 0, room_id: 0, date: '', start: '16:00', end: '17:30', topic: '' })
const rooms = ref<Room[]>([])
const error = ref<string | null>(null)
const busy = ref(false)

const group = computed(() => props.groups.find((g) => g.id === form.group_id))
const groupOptions = computed(() => [{ value: 0, label: t('schedule.pickGroup') }, ...props.groups.filter((g) => g.status !== 'finished').map((g) => ({ value: g.id, label: g.name }))])
const teacherOptions = computed(() => props.teachers.filter((x) => !group.value || !x.branchIds?.length || x.branchIds.includes(group.value.branch_id)).map((x) => ({ value: x.id, label: x.name })))
const roomOptions = computed(() => rooms.value.filter((r) => r.status === 'active').map((r) => ({ value: r.id, label: `${r.name} · ${r.capacity}` })))

watch(open, (v) => {
  if (!v) return
  Object.assign(form, { group_id: 0, teacher_id: 0, room_id: props.roomId ?? 0, date: props.date ?? isoDate(new Date()), start: '16:00', end: '17:30', topic: '' })
  error.value = null
})
watch(group, async (g) => {
  if (!g) return
  form.teacher_id = g.teacher_id
  rooms.value = await refs.roomsOf(g.branch_id)
  if (!rooms.value.some((r) => r.id === form.room_id)) form.room_id = g.room_id ?? rooms.value[0]?.id ?? 0
  const r = g.schedule[0]
  if (r) Object.assign(form, { start: r.start.slice(0, 5), end: r.end.slice(0, 5) })
})

async function submit() {
  error.value = !form.group_id ? t('schedule.pickGroup') : form.end <= form.start ? t('groups.rule.badTime') : !form.room_id ? t('groups.rule.roomRequired') : null
  if (error.value) return
  busy.value = true
  try {
    await academicsApi.createLesson({
      group_id: form.group_id, teacher_id: form.teacher_id, room_id: form.room_id,
      starts_at: new Date(`${form.date}T${form.start}`).toISOString(), ends_at: new Date(`${form.date}T${form.end}`).toISOString(),
      topic: form.topic.trim() || null,
    })
    toast.ok(t('schedule.createdToast'))
    emit('created')
    open.value = false
  } catch (e) {
    error.value = e instanceof ApiError ? e.detail || t('errors.generic') : t('errors.generic')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiModal v-model:open="open" :title="t('schedule.newLesson')">
    <form id="lc-form" class="stack" @submit.prevent="submit">
      <UiField :label="t('schedule.group')"><UiSelect v-model="form.group_id" :options="groupOptions" :label="t('schedule.group')" block /></UiField>
      <div class="form-3">
        <UiInput v-model="form.date" type="date" :label="t('schedule.date')" />
        <UiInput v-model="form.start" type="time" :label="t('groups.rule.start')" />
        <UiInput v-model="form.end" type="time" :label="t('groups.rule.end2')" />
      </div>
      <div class="form-2">
        <UiField :label="t('groups.room')"><UiSelect v-model="form.room_id" :options="roomOptions" :label="t('groups.room')" block :disabled="!group" /></UiField>
        <UiField :label="t('groups.teacher')"><UiSelect v-model="form.teacher_id" :options="teacherOptions" :label="t('groups.teacher')" block :disabled="!group" /></UiField>
      </div>
      <UiInput v-model="form.topic" :label="t('schedule.topic')" />
      <div v-if="error" class="alert red" role="alert"><UiIcon name="alert" /><div class="grow"><b>{{ error }}</b></div></div>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="primary" type="submit" form="lc-form" icon="plus" :loading="busy">{{ t('schedule.create') }}</UiButton>
    </template>
  </UiModal>
</template>
