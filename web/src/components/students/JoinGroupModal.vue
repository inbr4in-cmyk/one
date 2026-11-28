<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiField, UiIcon, UiInput, UiModal, UiSelect } from '@/components/ui'
import type { Student } from '@/api/students'
import { academicsApi, type Group } from '@/api/academics'
import { ApiError } from '@/api/http'
import { useToastStore } from '@/stores/toast'
import { addDays, isoDate, schoolNow, todayIso } from '@/utils/dates'

/** «Добавить в группу» right from the student card: pick a group of the branch and the first day in it. */
const props = defineProps<{ student: Student }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ done: [] }>()
const { t } = useI18n()
const toast = useToastStore()
const groups = ref<Group[]>([])
const target = ref(0)
const on = ref(todayIso())
const minOn = computed(() => isoDate(addDays(schoolNow(), -31)))
const error = ref<string | null>(null)
const busy = ref(false)

const current = computed(() => new Set(props.student.groups.filter((g) => !g.left_on).map((g) => g.id)))
const options = computed(() => [
  { value: 0, label: t('students.transfer.pick') },
  ...groups.value
    .filter((g) => !current.value.has(g.id) && g.status !== 'finished' && g.kind !== 'club')
    .map((g) => ({ value: g.id, label: `${g.name} · ${g.members}/${g.capacity}${g.teacher_name ? ` · ${g.teacher_name}` : ''}` })),
])
watch(open, async (v) => {
  if (!v) return
  target.value = 0
  on.value = todayIso()
  error.value = null
  groups.value = await academicsApi.groups({ branch_id: props.student.branch_id }).catch(() => [])
})
async function submit() {
  if (!target.value) return
  busy.value = true
  error.value = null
  try {
    await academicsApi.addMember(target.value, props.student.id, on.value === todayIso() ? undefined : on.value)
    toast.ok(t('nv.join.done'))
    open.value = false
    emit('done')
  } catch (e) {
    error.value = e instanceof ApiError ? e.detail || t('errors.generic') : t('errors.generic')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiModal v-model:open="open" :title="t('nv.join.title')">
    <form id="join-form" class="stack" @submit.prevent="submit">
      <UiField :label="t('nv.payp.group')"><UiSelect v-model="target" :options="options" :label="t('nv.payp.group')" block /></UiField>
      <UiInput v-model="on" type="date" :min="minOn" :max="isoDate(addDays(schoolNow(), 60))" :label="t('nv.join.since')" />
      <div v-if="error" class="alert red" role="alert"><UiIcon name="alert" /><div class="grow"><b>{{ error }}</b></div></div>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="primary" type="submit" form="join-form" :loading="busy" :disabled="!target">{{ t('nv.join.action') }}</UiButton>
    </template>
  </UiModal>
</template>
