<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiField, UiIcon, UiInput, UiModal, UiSegmented, UiSelect } from '@/components/ui'
import { useBranchStore } from '@/stores/branch'
import { academicsApi, type Group } from '@/api/academics'
import type { Room } from '@/api/org'
import { ApiError } from '@/api/http'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import type { TeacherOption } from '@/composables/useTeachers'
import { isoDate } from '@/utils/dates'

/** One-off lesson for a group (make-up, extra), or a support lesson (teacher + topic, no students).
 * The server refuses room/teacher conflicts with 409. */
const props = defineProps<{ groups: Group[]; teachers: TeacherOption[]; date?: string | null; roomId?: number | null
  start?: string | null; end?: string | null; branchId?: number | null }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ created: [] }>()
const { t } = useI18n()
const refs = useRefsStore()
const toast = useToastStore()
const mode = ref<'group' | 'support'>('group')
const modeOptions = computed(() => [{ value: 'group' as const, label: t('schedule.lessonFor') }, { value: 'support' as const, label: t('schedule.support.mode') }])
const branches = useBranchStore()
const branchOptions = computed(() => branches.options.filter((o) => o.id !== null).map((o) => ({ value: o.id as number, label: o.name })))
const supportBranch = ref(0)
const form = reactive({ group_id: 0, teacher_id: 0, room_id: 0, date: '', start: '16:00', end: '17:30', topic: '' })
const rooms = ref<Room[]>([])
const error = ref<string | null>(null)
const busy = ref(false)

const group = computed(() => props.groups.find((g) => g.id === form.group_id))
const groupOptions = computed(() => [{ value: 0, label: t('schedule.pickGroup') }, ...props.groups.filter((g) => g.status !== 'finished').map((g) => ({ value: g.id, label: g.name }))])
const branchOf = computed(() => (mode.value === 'support' ? supportBranch.value : group.value?.branch_id ?? 0))
const teacherOptions = computed(() => props.teachers.filter((x) => !branchOf.value || !x.branchIds?.length || x.branchIds.includes(branchOf.value)).map((x) => ({ value: x.id, label: x.name })))
const roomOptions = computed(() => rooms.value.filter((r) => r.status === 'active').map((r) => ({ value: r.id, label: `${r.name} · ${r.capacity}` })))

watch(open, (v) => {
  if (!v) return
  Object.assign(form, { group_id: 0, teacher_id: 0, room_id: props.roomId ?? 0, date: props.date ?? isoDate(new Date()),
    start: props.start ?? '16:00', end: props.end ?? '17:30', topic: '' })
  supportBranch.value = props.branchId ?? (branchOptions.value[0]?.value ?? 0)
  error.value = null
})
watch([mode, supportBranch], async () => {
  if (mode.value !== 'support' || !supportBranch.value) return
  rooms.value = await refs.roomsOf(supportBranch.value)
  if (!rooms.value.some((r) => r.id === form.room_id)) form.room_id = rooms.value.find((r) => r.status === 'active')?.id ?? 0
  if (!teacherOptions.value.some((x) => x.value === form.teacher_id)) form.teacher_id = 0
})
watch(group, async (g) => {
  if (!g) return
  form.teacher_id = g.teacher_id
  rooms.value = await refs.roomsOf(g.branch_id)
  if (!rooms.value.some((r) => r.id === form.room_id)) form.room_id = g.room_id ?? rooms.value[0]?.id ?? 0
  const r = g.schedule[0]
  if (r && !props.start) Object.assign(form, { start: r.start.slice(0, 5), end: r.end.slice(0, 5) })
})

async function submit() {
  const support = mode.value === 'support'
  error.value = support && !form.teacher_id ? t('schedule.support.pickTeacher') : support && !form.topic.trim() ? t('schedule.support.topicRequired')
    : !support && !form.group_id ? t('schedule.pickGroup') : form.end <= form.start ? t('groups.rule.badTime') : !form.room_id ? t('groups.rule.roomRequired') : null
  if (error.value) return
  busy.value = true
  try {
    await academicsApi.createLesson({
      ...(support ? { support: true } : { group_id: form.group_id }), teacher_id: form.teacher_id, room_id: form.room_id,
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
      <UiSegmented v-model="mode" :options="modeOptions" :label="t('schedule.newLesson')" size="sm" />
      <UiField v-if="mode === 'group'" :label="t('schedule.group')"><UiSelect v-model="form.group_id" :options="groupOptions" :label="t('schedule.group')" block /></UiField>
      <UiField v-else-if="branchOptions.length > 1" :label="t('schedule.support.branch')"><UiSelect v-model="supportBranch" :options="branchOptions" :label="t('schedule.support.branch')" block /></UiField>
      <div class="form-3">
        <UiInput v-model="form.date" type="date" :label="t('schedule.date')" />
        <UiInput v-model="form.start" type="time" :label="t('groups.rule.start')" />
        <UiInput v-model="form.end" type="time" :label="t('groups.rule.end2')" />
      </div>
      <div class="form-2">
        <UiField :label="t('groups.room')"><UiSelect v-model="form.room_id" :options="roomOptions" :label="t('groups.room')" block :disabled="mode === 'group' && !group" /></UiField>
        <UiField :label="t('groups.teacher')"><UiSelect v-model="form.teacher_id" :options="teacherOptions" :label="t('groups.teacher')" block :disabled="mode === 'group' && !group" /></UiField>
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
