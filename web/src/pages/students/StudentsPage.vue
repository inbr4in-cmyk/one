<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { UiAvatar, UiButton, UiCard, UiChip, UiEmptyState, UiInput, UiPager, UiPrompt, UiSelect, UiTable, type TableColumn } from '@/components/ui'
import StatusChip from '@/components/students/StatusChip.vue'
import LevelTag from '@/components/students/LevelTag.vue'
import StudentCreateDrawer from '@/components/students/StudentCreateDrawer.vue'
import { studentsApi, STUDENT_STATUSES, type StudentListItem } from '@/api/students'
import { academicsApi, type Group } from '@/api/academics'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import { useBranchStore } from '@/stores/branch'
import { useRefsStore } from '@/stores/refs'
import { dmy, money } from '@/utils/dates'
import type { Locale } from '@/i18n'

const LIMIT = 25
/** Filters survive leaving the page and coming back from a student card. */
const saved = reactive({ q: '', status: 'active', level_id: 0, group_id: 0, debt: false, offset: 0 })

const { t, locale } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const branch = useBranchStore()
const refs = useRefsStore()
const f = saved
// A link from the dashboard (?status=left / frozen) opens the list with that filter.
const route = useRoute()
if (typeof route.query.status === 'string') Object.assign(f, { q: '', status: route.query.status, level_id: 0, group_id: 0, debt: false, offset: 0 })
const rows = ref<StudentListItem[]>([])
const total = ref(0)
const loading = ref(true)
const groups = ref<Group[]>([])
const creating = ref(false)
let seq = 0

const loc = computed(() => locale.value as Locale)
const columns = computed<TableColumn[]>(() => [
  { key: 'full_name', label: t('students.col.name') },
  { key: 'group_names', label: t('students.col.groups') },
  { key: 'level_id', label: t('students.col.level') },
  { key: 'lessons_left', label: t('students.col.left'), align: 'right' },
  { key: 'money_balance', label: t('students.col.money'), align: 'right' },
  { key: 'last_visit_at', label: t('students.col.visit') },
  { key: 'status', label: t('students.col.status') },
  ...(auth.can('students.archive') ? [{ key: 'actions', label: '', align: 'right' as const }] : []),
])
const statusOptions = computed(() => [{ value: '', label: t('students.allStatuses') }, ...STUDENT_STATUSES.map((s) => ({ value: s, label: t(`students.status.${s}`) }))])
const levelOptions = computed(() => [{ value: 0, label: t('students.allLevels') }, ...refs.levels.map((l) => ({ value: l.id, label: l.name }))])
const groupOptions = computed(() => [{ value: 0, label: t('students.allGroups') }, ...groups.value.map((g) => ({ value: g.id, label: g.name }))])

/** «Удалить» in the list (owner, branch admin): the student goes to the archive, history stays. */
const toast = useToastStore()
const del = ref<StudentListItem | null>(null)
const delBusy = ref(false)
async function doDelete() {
  if (!del.value) return
  delBusy.value = true
  try {
    await studentsApi.archive(del.value.id)
    toast.ok(t('students.archived'))
    del.value = null
    await load()
  } finally {
    delBusy.value = false
  }
}

async function load() {
  const my = ++seq
  loading.value = true
  try {
    const page = await studentsApi.list({
      q: f.q.trim() || undefined,
      branch_id: branch.filterId,
      status: f.status || undefined,
      level_id: f.level_id || null,
      group_id: f.group_id || null,
      debt: f.debt,
      limit: LIMIT,
      offset: f.offset,
    })
    if (my !== seq) return
    rows.value = page.items
    total.value = page.total
  } catch {
    if (my === seq) rows.value = []
  } finally {
    if (my === seq) loading.value = false
  }
}

let timer: ReturnType<typeof setTimeout> | undefined
watch(() => f.q, () => {
  clearTimeout(timer)
  timer = setTimeout(() => (f.offset === 0 ? load() : (f.offset = 0)), 300)
})
watch(() => [f.status, f.level_id, f.group_id, f.debt, branch.filterId], () => (f.offset === 0 ? load() : (f.offset = 0)))
watch(() => f.offset, load)

onMounted(async () => {
  load()
  if (auth.can('schedule.view')) groups.value = await academicsApi.groups({ branch_id: branch.filterId }).catch(() => [])
})

const open = (row: StudentListItem) => router.push({ name: 'student', params: { id: row.id } })
const hasFilters = computed(() => !!(f.q || f.level_id || f.group_id || f.debt || f.status !== 'active'))
function resetFilters() {
  Object.assign(f, { q: '', status: 'active', level_id: 0, group_id: 0, debt: false, offset: 0 })
}
</script>

<template>
  <div class="ph">
    <div><h1>{{ t('students.title') }}</h1><p>{{ t('students.subtitle', { n: total }) }}</p></div>
    <span class="sp" />
    <UiButton v-if="auth.can('students.create')" icon="file" to="/students/import">{{ t('import.action') }}</UiButton>
    <UiButton v-if="auth.can('students.create')" variant="primary" icon="plus" @click="creating = true">{{ t('students.new') }}</UiButton>
  </div>

  <div class="toolbar">
    <UiInput v-model="f.q" type="search" icon="search" :placeholder="t('students.searchPh')" class="tb-search" />
    <UiSelect v-model="f.status" :options="statusOptions" :label="t('students.col.status')" />
    <UiSelect v-model="f.level_id" :options="levelOptions" :label="t('students.col.level')" />
    <UiSelect v-if="groups.length" v-model="f.group_id" :options="groupOptions" :label="t('students.col.groups')" />
    <button type="button" class="tgl" :aria-pressed="f.debt" @click="f.debt = !f.debt">{{ t('students.debtOnly') }}</button>
    <UiButton v-if="hasFilters" size="sm" variant="ghost" icon="x" @click="resetFilters">{{ t('common.reset') }}</UiButton>
  </div>

  <UiCard flush>
    <UiTable :columns="columns" :rows="rows" :loading="loading" hover @row-click="open">
      <template #cell-full_name="{ row }">
        <RouterLink :to="{ name: 'student', params: { id: row.id } }" class="who2 rowlink" @click.stop>
          <UiAvatar :name="row.full_name" size="sm" />
          <span><b>{{ row.full_name }}</b><small v-if="row.age !== null" class="muted"> · {{ t('students.age', { n: row.age }) }}</small></span>
        </RouterLink>
      </template>
      <template #cell-group_names="{ row }">
        <span v-if="row.group_names.length" class="chips">{{ row.group_names.join(', ') }}</span>
        <span v-else class="muted">—</span>
      </template>
      <template #cell-level_id="{ row }"><LevelTag :id="row.level_id" /></template>
      <template #cell-lessons_left="{ row }">
        <b class="num" :class="{ warnc: row.lessons_left <= 2 && row.lessons_left > 0, redc: row.lessons_left <= 0 }">{{ row.lessons_left }}</b>
      </template>
      <template #cell-money_balance="{ row }">
        <span class="num" :class="{ redc: row.money_balance < 0 }">{{ money(row.money_balance, loc) }}</span>
      </template>
      <template #cell-last_visit_at="{ row }">
        <span class="num muted">{{ row.last_visit_at ? dmy(row.last_visit_at, loc) : '—' }}</span>
      </template>
      <template #cell-status="{ row }">
        <StatusChip :status="row.status" small />
        <UiChip v-if="row.lessons_left <= 0 && row.status === 'active'" tone="red" small>{{ t('students.debt') }}</UiChip>
      </template>
      <template #cell-actions="{ row }">
        <UiButton size="sm" variant="ghost" danger icon="delete" :aria-label="`${t('students.archive')}: ${row.full_name}`" @click.stop="del = row" />
      </template>
      <template #empty>
        <UiEmptyState icon="users" :title="t('students.empty')" :text="hasFilters ? t('students.emptyFiltered') : undefined" />
      </template>
    </UiTable>
    <UiPager v-model="f.offset" :total="total" :limit="LIMIT" />
  </UiCard>

  <StudentCreateDrawer v-model:open="creating" @created="(s) => open(s)" />
  <UiPrompt :open="!!del" :title="t('students.archive')" :text="t('students.archiveText', { name: del?.full_name ?? '' })" :confirm-label="t('students.archive')"
    danger :busy="delBusy" @update:open="(v) => !v && (del = null)" @confirm="doDelete" />
</template>
