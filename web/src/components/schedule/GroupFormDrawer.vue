<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiDrawer, UiField, UiInput, UiSegmented, UiSelect } from '@/components/ui'
import { academicsApi, COURSE_KINDS, KIND_ICON, type CourseKind, type Group } from '@/api/academics'
import type { Room } from '@/api/org'
import { ApiError } from '@/api/http'
import { useBranchStore } from '@/stores/branch'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'

/** Create a group, or edit one when `group` is given. */
const props = defineProps<{ group?: Group | null; teachers: { id: number; name: string; branchIds?: number[] }[] }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ saved: [Group] }>()
const { t } = useI18n()
const branch = useBranchStore()
const refs = useRefsStore()
const toast = useToastStore()

const form = reactive({ kind: 'group' as CourseKind, name: '', branch_id: 0, level_id: 0, teacher_id: 0, room_id: 0, capacity: '12', starts_on: '', status: 'recruiting' as Group['status'] })
const rooms = ref<Room[]>([])
const errors = reactive<Record<string, string | null>>({})
const busy = ref(false)

const branchOptions = computed(() => branch.options.filter((o) => o.id !== null).map((o) => ({ value: o.id as number, label: o.name })))
const levelOptions = computed(() => [{ value: 0, label: '—' }, ...refs.levels.map((l) => ({ value: l.id, label: l.name }))])
const teacherOptions = computed(() => [{ value: 0, label: '—' }, ...props.teachers.filter((x) => !x.branchIds?.length || x.branchIds.includes(form.branch_id)).map((x) => ({ value: x.id, label: x.name }))])
const roomOptions = computed(() => [{ value: 0, label: t('groups.noRoom') }, ...rooms.value.filter((r) => r.status === 'active').map((r) => ({ value: r.id, label: `${r.name} · ${r.capacity}` }))])
const kindOptions = computed(() => COURSE_KINDS.map((k) => ({ value: k, label: t(`kind.${k}`), icon: KIND_ICON[k] })))
const KIND_CAP: Partial<Record<CourseKind, number>> = { individual: 1, duo: 2 }
watch(() => form.kind, (k) => {
  const cap = KIND_CAP[k]
  if (cap) form.capacity = String(cap)
  else if (Number(form.capacity) <= 2) form.capacity = '12'
})
const statusOptions = computed(() => (['recruiting', 'active', 'finished'] as const).map((s) => ({ value: s, label: t(`groups.status.${s}`) })))

watch(open, (v) => {
  if (!v) return
  const g = props.group
  Object.keys(errors).forEach((k) => (errors[k] = null))
  Object.assign(form, g
    ? { kind: g.kind ?? 'group', name: g.name, branch_id: g.branch_id, level_id: g.level_id ?? 0, teacher_id: g.teacher_id, room_id: g.room_id ?? 0, capacity: String(g.capacity), starts_on: g.starts_on ?? '', status: g.status }
    : { kind: 'group', name: '', branch_id: branch.filterId ?? branchOptions.value[0]?.value ?? 0, level_id: 0, teacher_id: 0, room_id: 0, capacity: '12', starts_on: '', status: 'recruiting' })
})
watch(() => form.branch_id, async (id) => {
  rooms.value = id ? await refs.roomsOf(id) : []
  if (!rooms.value.some((r) => r.id === form.room_id)) form.room_id = 0
}, { immediate: true })

async function submit() {
  Object.keys(errors).forEach((k) => (errors[k] = null))
  if (form.name.trim().length < 2) errors.name = t('students.form.nameRequired')
  if (!form.level_id && form.kind !== 'club') errors.level = t('groups.levelRequired')
  if (!form.teacher_id) errors.teacher = t('groups.teacherRequired')
  if (Object.values(errors).some(Boolean)) return
  busy.value = true
  const body = {
    name: form.name.trim(), branch_id: form.branch_id, level_id: form.kind === 'club' ? null : form.level_id, teacher_id: form.teacher_id,
    room_id: form.room_id || null, capacity: Math.max(1, Number(form.capacity) || 1), starts_on: form.starts_on || null, status: form.status,
    kind: form.kind,
  }
  try {
    const g = props.group ? await academicsApi.updateGroup(props.group.id, body) : await academicsApi.createGroup(body)
    toast.ok(props.group ? t('common.saved') : t('groups.created'))
    emit('saved', g)
    open.value = false
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) errors.name = e.detail
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiDrawer v-model:open="open" :title="group ? t('groups.edit') : t('groups.new')">
    <form id="grp-form" class="stack" novalidate @submit.prevent="submit">
      <UiField :label="t('kind.label')" :hint="t('kind.hint')">
        <UiSegmented v-model="form.kind" :options="kindOptions" :label="t('kind.label')" size="sm" />
      </UiField>
      <UiInput v-model="form.name" :label="t('groups.name')" :placeholder="t('groups.namePh')" :error="errors.name" autofocus />
      <UiField v-if="!group" :label="t('branch.label')"><UiSelect v-model="form.branch_id" :options="branchOptions" :label="t('branch.label')" block /></UiField>
      <p v-if="form.kind === 'club'" class="form-note">{{ t('kind.clubHint') }}</p>
      <div class="form-2">
        <UiField v-if="form.kind !== 'club'" :label="t('students.form.level')" :error="errors.level"><UiSelect v-model="form.level_id" :options="levelOptions" :label="t('students.form.level')" block /></UiField>
        <UiField :label="t('groups.teacher')" :error="errors.teacher"><UiSelect v-model="form.teacher_id" :options="teacherOptions" :label="t('groups.teacher')" block /></UiField>
      </div>
      <div class="form-2">
        <UiField :label="t('groups.room')"><UiSelect v-model="form.room_id" :options="roomOptions" :label="t('groups.room')" block /></UiField>
        <UiInput v-model="form.capacity" type="number" :min="1" :max="40" :label="t('groups.capacity')" :disabled="form.kind !== 'group'" v-if="form.kind !== 'club'" />
      </div>
      <div class="form-2">
        <UiInput v-model="form.starts_on" type="date" :label="t('groups.startsOn')" />
        <UiField :label="t('students.col.status')"><UiSelect v-model="form.status" :options="statusOptions" :label="t('students.col.status')" block /></UiField>
      </div>
      <p v-if="!teachers.length" class="form-note">{{ t('groups.noTeachers') }}</p>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="primary" type="submit" form="grp-form" :loading="busy">{{ group ? t('common.save') : t('groups.create') }}</UiButton>
    </template>
  </UiDrawer>
</template>
