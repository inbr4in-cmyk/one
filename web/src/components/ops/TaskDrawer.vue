<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiDrawer, UiField, UiInput, UiSegmented, UiSelect, UiTextarea } from '@/components/ui'
import StaffMultiPicker from './StaffMultiPicker.vue'
import LinkPicker from './LinkPicker.vue'
import { tasksApi, type Task, type TaskLink, type TaskPriority } from '@/api/tasks'
import { ApiError } from '@/api/http'
import { useBranchStore } from '@/stores/branch'
import { useToastStore } from '@/stores/toast'
import { localInput, toSchool, wallToIso } from '@/utils/dates'

/** New task, or edit one you created (title, text, due, priority, assignees). */
const props = defineProps<{ task?: Task | null; preset?: { type: TaskLink; id: number; title: string } | null }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ saved: [Task] }>()
const { t } = useI18n()
const branch = useBranchStore()
const toast = useToastStore()

const form = reactive({
  title: '', description: '', due: '', priority: 'normal' as TaskPriority, assignees: [] as number[],
  recurrence: '' as '' | 'daily' | 'weekly', branch_id: 0, link: null as { type: TaskLink; id: number; title: string } | null,
})
const errors = reactive<Record<string, string | null>>({})
const busy = ref(false)
const priorities = computed(() => (['low', 'normal', 'high'] as const).map((p) => ({ value: p, label: t(`tasks.priority.${p}`) })))
const recurrences = computed(() => [{ value: '' as const, label: t('tasks.once') }, { value: 'daily' as const, label: t('tasks.daily') }, { value: 'weekly' as const, label: t('tasks.weekly') }])
const branchOptions = computed(() => [{ value: 0, label: t('tasks.noBranch') }, ...branch.options.filter((o) => o.id !== null).map((o) => ({ value: o.id as number, label: o.name }))])

watch(open, (v) => {
  if (!v) return
  Object.keys(errors).forEach((k) => (errors[k] = null))
  const x = props.task
  Object.assign(form, x
    ? { title: x.title, description: x.description ?? '', due: x.due_at ? localInput(toSchool(x.due_at)) : '', priority: x.priority, assignees: x.assignees.map((a) => a.id), recurrence: x.recurrence ?? '', branch_id: x.branch_id ?? 0, link: null }
    : { title: '', description: '', due: '', priority: 'normal', assignees: [], recurrence: '', branch_id: branch.filterId ?? 0, link: props.preset ?? null })
})

async function submit() {
  Object.keys(errors).forEach((k) => (errors[k] = null))
  if (form.title.trim().length < 2) errors.title = t('tasks.titleRequired')
  if (!form.assignees.length) errors.assignees = t('tasks.assigneeRequired')
  if (Object.values(errors).some(Boolean)) return
  busy.value = true
  const due_at = form.due ? wallToIso(form.due) : null
  try {
    const saved = props.task
      ? await tasksApi.patch(props.task.id, { title: form.title.trim(), description: form.description.trim() || null, priority: form.priority, due_at, assignee_ids: form.assignees })
      : await tasksApi.create({
        title: form.title.trim(), description: form.description.trim() || null, priority: form.priority, due_at, assignee_ids: form.assignees,
        branch_id: form.branch_id || null, recurrence: form.recurrence || null, link_type: form.link?.type ?? null, link_id: form.link?.id ?? null,
      })
    toast.ok(props.task ? t('common.saved') : t('tasks.created'))
    emit('saved', saved)
    open.value = false
  } catch (e) {
    errors.form = e instanceof ApiError ? e.detail || t('errors.generic') : t('errors.generic')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiDrawer v-model:open="open" :title="task ? t('tasks.edit') : t('tasks.newTitle')">
    <form id="task-form" class="stack" novalidate @submit.prevent="submit">
      <UiInput v-model="form.title" :label="t('tasks.titleLabel')" :placeholder="t('tasks.titlePh')" :error="errors.title" :maxlength="255" autofocus />
      <UiTextarea v-model="form.description" :label="t('tasks.description')" :rows="3" :maxlength="8000" />
      <UiField :label="t('tasks.priorityLabel')"><UiSegmented v-model="form.priority" :options="priorities" :label="t('tasks.priorityLabel')" block /></UiField>
      <UiInput v-model="form.due" type="datetime-local" :label="t('tasks.due')" />
      <div v-if="!task" class="form-2">
        <UiField :label="t('tasks.repeat')"><UiSelect v-model="form.recurrence" :options="recurrences" :label="t('tasks.repeat')" block /></UiField>
        <UiField :label="t('branch.label')"><UiSelect v-model="form.branch_id" :options="branchOptions" :label="t('branch.label')" block /></UiField>
      </div>
      <UiField :label="t('tasks.assignees')" :error="errors.assignees"><StaffMultiPicker v-model="form.assignees" :branch-id="form.branch_id || null" /></UiField>
      <UiField v-if="!task" :label="t('tasks.linkLabel')"><LinkPicker v-model="form.link" /></UiField>
      <p v-if="errors.form" class="form-err" role="alert">{{ errors.form }}</p>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="primary" type="submit" form="task-form" :loading="busy">{{ task ? t('common.save') : t('tasks.create') }}</UiButton>
    </template>
  </UiDrawer>
</template>
