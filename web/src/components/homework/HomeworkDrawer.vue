<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiAvatar, UiButton, UiChip, UiDrawer, UiEmptyState, UiIcon, UiPrompt, UiSegmented, UiSkeleton, UiTextarea } from '@/components/ui'
import { academicsApi, type Homework, type HomeworkSubmission, type SubmissionStatus } from '@/api/academics'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import { dmy, hm } from '@/utils/dates'
import { apiErr } from '@/utils/err'
import { safeUrl } from '@/utils/url'
import type { Locale } from '@/i18n'

/** One homework: who handed in what, grading with a comment, edit and archive. */
const props = defineProps<{ homework: Homework | null }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ edit: [h: Homework]; changed: [] }>()
const { t, locale } = useI18n()
const auth = useAuthStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)
const canManage = computed(() => auth.can('homework.manage'))

type Filter = 'all' | 'submitted' | 'assigned' | 'checked'
const filter = ref<Filter>('all')
const rows = ref<HomeworkSubmission[] | null>(null)
const failed = ref(false)
const checking = ref<number | null>(null)
const form = reactive({ grade: 0, comment: '' })
const busy = ref(false)
const error = ref<string | null>(null)
const archiving = ref(false)
/** Graded in this view: they stay in place until the filter changes, so the list does not jump */
const justChecked = ref(new Set<number>())
watch(filter, () => (justChecked.value = new Set()))

const TONE: Record<SubmissionStatus, 'ok' | 'info' | undefined> = { assigned: undefined, submitted: 'info', checked: 'ok' }
const counts = computed(() => {
  const r = rows.value ?? []
  return { all: r.length, submitted: r.filter((x) => x.status === 'submitted').length, assigned: r.filter((x) => x.status === 'assigned').length, checked: r.filter((x) => x.status === 'checked').length }
})
const filters = computed(() => (['all', 'submitted', 'assigned', 'checked'] as const).map((f) => ({ value: f, label: `${t(`hw.f.${f}`)} ${counts.value[f]}` })))
const shown = computed(() => (rows.value ?? []).filter((r) => filter.value === 'all' || r.status === filter.value || justChecked.value.has(r.student_id)))
const grades = computed(() => [{ value: 0, label: '—' }, ...[1, 2, 3, 4, 5].map((n) => ({ value: n, label: String(n) }))])
const overdue = computed(() => !!props.homework?.due_at && new Date(props.homework.due_at) < new Date())

async function load() {
  const h = props.homework
  if (!h) return
  rows.value = null
  failed.value = false
  try {
    rows.value = await academicsApi.submissions(h.id)
    // Start where the work is: handed in and waiting for a check
    filter.value = rows.value.some((r) => r.status === 'submitted') ? 'submitted' : 'all'
  } catch {
    failed.value = true
  }
}
watch([open, () => props.homework?.id], () => {
  if (open.value) {
    checking.value = null
    load()
  }
}, { immediate: true })

function startCheck(r: HomeworkSubmission) {
  checking.value = r.student_id
  form.grade = r.grade ?? 0
  form.comment = r.teacher_comment ?? ''
  error.value = null
}
async function saveCheck(r: HomeworkSubmission) {
  const h = props.homework
  if (!h) return
  busy.value = true
  error.value = null
  try {
    const body = { grade: form.grade || null, comment: form.comment.trim() || null }
    await academicsApi.check(h.id, r.student_id, body)
    justChecked.value = new Set([...justChecked.value, r.student_id])
    Object.assign(r, { status: 'checked', grade: body.grade, teacher_comment: body.comment })
    checking.value = null
    toast.ok(t('hw.checked', { name: r.full_name.split(' ')[0] }))
    emit('changed')
  } catch (e) {
    error.value = apiErr(e) ?? t('errors.generic')
  } finally {
    busy.value = false
  }
}
async function archive() {
  const h = props.homework
  if (!h) return
  busy.value = true
  try {
    await academicsApi.archiveHomework(h.id)
    toast.ok(t('hw.archived'))
    archiving.value = false
    open.value = false
    emit('changed')
  } finally {
    busy.value = false
  }
}
const when = (iso: string) => `${dmy(iso, loc.value)} ${hm(iso, loc.value)}`
</script>

<template>
  <UiDrawer v-model:open="open" :title="homework?.title ?? t('groups.hw.title')">
    <div v-if="homework" class="stack">
      <div class="chips-row">
        <UiChip v-if="homework.due_at" :tone="overdue ? 'warn' : undefined" icon="clock">{{ t('hw.dueAt', { date: when(homework.due_at) }) }}</UiChip>
        <UiChip v-else>{{ t('portal.hw.noDue') }}</UiChip>
        <span class="muted" style="font-size: 12.5px">{{ t('hw.givenAt', { date: dmy(homework.created_at, loc) }) }}</span>
      </div>
      <p v-if="homework.body" class="hw-body">{{ homework.body }}</p>
      <div v-if="canManage" class="row-acts" style="justify-content: flex-start">
        <UiButton size="sm" icon="edit" @click="emit('edit', homework)">{{ t('common.edit') }}</UiButton>
        <UiButton size="sm" variant="ghost" icon="archive" @click="archiving = true">{{ t('hw.archive') }}</UiButton>
      </div>

      <h4 class="m0">{{ t('hw.submissions') }}</h4>
      <UiSkeleton v-if="!rows && !failed" :lines="5" />
      <UiEmptyState v-else-if="failed" icon="alert" :title="t('errors.generic')"><UiButton size="sm" @click="load">{{ t('common.retry') }}</UiButton></UiEmptyState>
      <template v-else-if="rows">
        <UiSegmented v-model="filter" :options="filters" :label="t('hw.submissions')" size="sm" class="wrap" />
        <UiEmptyState v-if="!shown.length" icon="homework" :title="t('hw.noneHere')" />
        <div v-for="r in shown" :key="r.student_id" class="hw-sub" :class="r.status">
          <div class="hw-sub-h">
            <UiAvatar :name="r.full_name" size="sm" />
            <div class="grow">
              <b>{{ r.full_name }}</b>
              <span v-if="r.submitted_at && r.status !== 'assigned'">{{ t('hw.handedIn', { date: when(r.submitted_at) }) }}</span>
            </div>
            <span v-if="r.grade" class="hw-grade num" :aria-label="t('portal.grade')">{{ r.grade }}</span>
            <UiChip :tone="TONE[r.status]" small>{{ t(`hw.st.${r.status}`) }}</UiChip>
            <UiButton v-if="canManage && r.status === 'assigned' && checking !== r.student_id" size="sm" variant="ghost" icon="edit" :aria-label="t('hw.gradeOffline')" :title="t('hw.gradeOffline')" @click="startCheck(r)" />
          </div>
          <p v-if="r.answer" class="hw-answer">{{ r.answer }}</p>
          <a v-if="r.file_url && safeUrl(r.file_url)" :href="safeUrl(r.file_url)!" target="_blank" rel="noopener noreferrer" class="hw-file"><UiIcon name="clip" :size="14" />{{ t('portal.hw.file') }}</a>
          <p v-if="r.teacher_comment && checking !== r.student_id" class="hw-comment"><b>{{ t('portal.hw.teacher') }}:</b> {{ r.teacher_comment }}</p>

          <form v-if="checking === r.student_id" class="stack hw-check" @submit.prevent="saveCheck(r)">
            <div class="hw-grade-row"><span>{{ t('portal.grade') }}</span><UiSegmented v-model="form.grade" :options="grades" :label="t('portal.grade')" size="sm" /></div>
            <UiTextarea v-model="form.comment" :label="t('portal.hw.teacher')" :placeholder="t('hw.commentPh')" :rows="2" :maxlength="1000" />
            <p v-if="error" class="form-err" role="alert">{{ error }}</p>
            <div class="row-acts" style="justify-content: flex-start">
              <UiButton type="submit" size="sm" variant="navy" icon="ok" :loading="busy">{{ t('hw.saveCheck') }}</UiButton>
              <UiButton size="sm" variant="ghost" @click="checking = null">{{ t('common.cancel') }}</UiButton>
            </div>
          </form>
          <div v-else-if="canManage && r.status !== 'assigned'" class="row-acts" style="justify-content: flex-start">
            <UiButton size="sm" :variant="r.status === 'submitted' ? 'navy' : 'ghost'" @click="startCheck(r)">{{ r.status === 'checked' ? t('hw.recheck') : t('hw.check') }}</UiButton>
          </div>
        </div>
      </template>
    </div>
  </UiDrawer>
  <UiPrompt :open="archiving" :title="t('hw.archiveTitle')" :text="t('hw.archiveText')" :confirm-label="t('hw.archive')" danger :busy="busy" @update:open="(v) => (archiving = v)" @confirm="archive" />
</template>
