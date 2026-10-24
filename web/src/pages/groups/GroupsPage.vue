<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { UiButton, UiCard, UiChip, UiEmptyState, UiInput, UiSelect, UiTable, type TableColumn } from '@/components/ui'
import LevelTag from '@/components/students/LevelTag.vue'
import GroupFormDrawer from '@/components/schedule/GroupFormDrawer.vue'
import { academicsApi, type Group } from '@/api/academics'
import { useAuthStore } from '@/stores/auth'
import { useBranchStore } from '@/stores/branch'
import { useRefsStore } from '@/stores/refs'
import { useTeachers } from '@/composables/useTeachers'
import { ruleSummary } from '@/utils/dates'
import { tone } from '@/utils/levels'
import type { Locale } from '@/i18n'

const { t, locale } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const branch = useBranchStore()
const refs = useRefsStore()
const loc = computed(() => locale.value as Locale)

const groups = ref<Group[]>([])
const loading = ref(true)
const q = ref('')
const level = ref(0)
const status = ref<'' | Group['status']>('')
const creating = ref(false)
const teachers = useTeachers()

const columns = computed<TableColumn[]>(() => [
  { key: 'name', label: t('groups.name') },
  { key: 'level_id', label: t('students.col.level') },
  { key: 'teacher_name', label: t('groups.teacher') },
  { key: 'schedule', label: t('nav.schedule') },
  { key: 'members', label: t('groups.members'), align: 'right' },
  { key: 'status', label: t('students.col.status') },
])
const levelOptions = computed(() => [{ value: 0, label: t('students.allLevels') }, ...refs.levels.map((l) => ({ value: l.id, label: l.name }))])
const statusOptions = computed(() => [{ value: '' as const, label: t('students.allStatuses') }, ...(['recruiting', 'active', 'finished'] as const).map((s) => ({ value: s, label: t(`groups.status.${s}`) }))])

const shown = computed(() => {
  const s = q.value.trim().toLowerCase()
  return groups.value.filter((g) =>
    (!s || g.name.toLowerCase().includes(s) || (g.teacher_name ?? '').toLowerCase().includes(s)) &&
    (!level.value || g.level_id === level.value) && (!status.value || g.status === status.value))
})

async function load() {
  loading.value = true
  try {
    groups.value = await academicsApi.groups({ branch_id: branch.filterId })
  } catch {
    groups.value = []
  } finally {
    loading.value = false
  }
}
watch(() => branch.filterId, load)
onMounted(load)

const STATUS_TONE = { recruiting: 'info', active: 'ok', finished: undefined } as const
const fill = (g: Group) => Math.min(100, Math.round((g.members / Math.max(1, g.capacity)) * 100))
</script>

<template>
  <div class="ph">
    <div><h1>{{ t('groups.title') }}</h1><p>{{ t('groups.subtitle', { n: groups.length }) }}</p></div>
    <span class="sp" />
    <UiButton v-if="auth.can('schedule.create')" variant="primary" icon="plus" @click="creating = true">{{ t('groups.new') }}</UiButton>
  </div>

  <div class="toolbar">
    <UiInput v-model="q" type="search" icon="search" :placeholder="t('groups.searchPh')" class="tb-search" />
    <UiSelect v-model="level" :options="levelOptions" :label="t('students.col.level')" />
    <UiSelect v-model="status" :options="statusOptions" :label="t('students.col.status')" />
  </div>

  <UiCard flush>
    <UiTable :columns="columns" :rows="shown" :loading="loading" hover @row-click="(g) => router.push(`/groups/${g.id}`)">
      <template #cell-name="{ row }">
        <RouterLink :to="`/groups/${row.id}`" class="who2 rowlink" @click.stop>
          <span class="gav" :style="{ '--c': tone(refs.level(row.level_id)?.color) }">{{ row.name.slice(0, 2) }}</span>
          <span><b>{{ row.name }}</b><small class="muted"> · {{ refs.branchName(row.branch_id) }}</small></span>
        </RouterLink>
      </template>
      <template #cell-level_id="{ row }"><LevelTag :id="row.level_id" /></template>
      <template #cell-teacher_name="{ row }">{{ row.teacher_name ?? '—' }}</template>
      <template #cell-schedule="{ row }">
        <span v-if="row.schedule.length" class="num">{{ ruleSummary(row.schedule, loc) }}</span>
        <UiChip v-else tone="warn" small>{{ t('groups.noSchedule') }}</UiChip>
      </template>
      <template #cell-members="{ row }">
        <div class="fill-cell"><b class="num">{{ row.members }}/{{ row.capacity }}</b><span class="bar-track"><i :style="{ width: `${fill(row)}%`, background: fill(row) >= 100 ? 'var(--red)' : undefined }" /></span></div>
      </template>
      <template #cell-status="{ row }"><UiChip :tone="STATUS_TONE[row.status]" small>{{ t(`groups.status.${row.status}`) }}</UiChip></template>
      <template #empty><UiEmptyState icon="groups" :title="t('groups.empty')" /></template>
    </UiTable>
  </UiCard>

  <GroupFormDrawer v-model:open="creating" :teachers="teachers" @saved="(g) => router.push(`/groups/${g.id}`)" />
</template>
