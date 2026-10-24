<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { UiButton, UiCard, UiChip, UiEmptyState, UiIcon, UiPager, UiSelect, UiSkeleton, UiTabs } from '@/components/ui'
import TaskDrawer from '@/components/ops/TaskDrawer.vue'
import { STATUS_TONE } from '@/components/ops/taskMeta'
import { tasksApi, type Task, type TaskStatus } from '@/api/tasks'
import { useAuthStore } from '@/stores/auth'
import { useBranchStore } from '@/stores/branch'
import { useCountersStore } from '@/stores/counters'
import { relativeTime } from '@/utils/format'
import { dayLabel, hm } from '@/utils/dates'
import type { Locale } from '@/i18n'

const LIMIT = 30
const { t, locale } = useI18n()
const auth = useAuthStore()
const branch = useBranchStore()
const counters = useCountersStore()
const router = useRouter()
const loc = computed(() => locale.value as Locale)

type Box = 'mine' | 'created' | 'all'
const f = reactive({ box: 'mine' as Box, status: '' as TaskStatus | '', overdue: false, offset: 0 })
const rows = ref<Task[]>([])
const total = ref(0)
const loading = ref(true)
const drawer = ref(false)
let seq = 0

const boxes = computed(() => [
  { value: 'mine' as const, label: t('tasks.box.mine') },
  ...(auth.can('tasks.create') ? [{ value: 'created' as const, label: t('tasks.box.created') }] : []),
  ...(auth.can('tasks.view', 'branch') ? [{ value: 'all' as const, label: t('tasks.box.all') }] : []),
])
const statusOptions = computed(() => [{ value: '' as const, label: f.box === 'all' ? t('tasks.anyStatus') : t('tasks.openOnly') },
  ...(['new', 'in_progress', 'review', 'done', 'cancelled'] as const).map((s) => ({ value: s, label: t(`tasks.status.${s}`) }))])

async function load() {
  const my = ++seq
  loading.value = true
  try {
    const page = await tasksApi.list({ box: f.box, status: f.status, overdue: f.overdue, branch_id: f.box === 'all' ? branch.filterId : null, limit: LIMIT, offset: f.offset })
    if (my !== seq) return
    rows.value = page.items
    total.value = page.total
  } catch {
    if (my === seq) rows.value = []
  } finally {
    if (my === seq) loading.value = false
  }
}
watch(() => [f.box, f.status, f.overdue, branch.filterId], () => (f.offset === 0 ? load() : (f.offset = 0)))
watch(() => f.offset, load)
onMounted(load)

const dueText = (x: Task) => (x.due_at ? `${dayLabel(x.due_at, loc.value)}, ${hm(x.due_at, loc.value)}` : t('tasks.noDue'))
function created(x: Task) {
  counters.refresh()
  router.push(`/tasks/${x.id}`)
}
</script>

<template>
  <div class="ph">
    <div><h1>{{ t('nav.tasks') }}</h1><p>{{ t('tasks.subtitle') }}</p></div>
    <span class="sp" />
    <UiButton v-if="auth.can('tasks.create')" variant="primary" icon="plus" @click="drawer = true">{{ t('tasks.new') }}</UiButton>
  </div>

  <UiTabs v-model="f.box" :items="boxes" :label="t('nav.tasks')" />
  <div class="toolbar">
    <UiSelect v-model="f.status" :options="statusOptions" :label="t('tasks.statusLabel')" />
    <button type="button" class="tgl" :aria-pressed="f.overdue" @click="f.overdue = !f.overdue"><UiIcon name="clock" :size="16" />{{ t('tasks.overdueOnly') }}</button>
  </div>

  <UiCard flush>
    <div v-if="loading && !rows.length" class="card-pad"><UiSkeleton :lines="5" /></div>
    <div v-else-if="rows.length" class="lr-list task-list">
      <RouterLink v-for="x in rows" :key="x.id" :to="`/tasks/${x.id}`" class="list-row task-row" :class="{ overdue: x.overdue, done: x.status === 'done' || x.status === 'cancelled' }">
        <span class="prio" :class="x.priority" :title="t(`tasks.priority.${x.priority}`)" />
        <div class="grow">
          <b>{{ x.title }}</b>
          <span>
            {{ x.assignees.map((a) => a.full_name).join(', ') }}
            <template v-if="f.box === 'mine' && x.creator_name"> · {{ t('tasks.from', { name: x.creator_name }) }}</template>
            <template v-if="x.comments"> · <UiIcon name="chat" :size="14" /> {{ x.comments }}</template>
            <template v-if="x.recurrence"> · {{ t(`tasks.${x.recurrence}`) }}</template>
          </span>
        </div>
        <div class="task-side">
          <UiChip :tone="STATUS_TONE[x.status]" small>{{ t(`tasks.status.${x.status}`) }}</UiChip>
          <span class="due num" :class="{ redc: x.overdue }"><UiIcon v-if="x.overdue" name="alert" :size="14" />{{ x.overdue ? t('tasks.overdue', { when: relativeTime(x.due_at!, loc) }) : dueText(x) }}</span>
        </div>
      </RouterLink>
    </div>
    <UiEmptyState v-else icon="task" :title="f.overdue ? t('tasks.noOverdue') : t('tasks.empty')" />
    <UiPager v-model="f.offset" :total="total" :limit="LIMIT" />
  </UiCard>

  <TaskDrawer v-model:open="drawer" @saved="created" />
</template>
