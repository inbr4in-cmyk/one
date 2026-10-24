<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { UiAvatar, UiButton, UiCard, UiChip, UiEmptyState, UiIcon, UiPrompt, UiSkeleton } from '@/components/ui'
import TaskDrawer from '@/components/ops/TaskDrawer.vue'
import { linkRoute, nextStatuses, STATUS_TONE } from '@/components/ops/taskMeta'
import { tasksApi, type Task, type TaskComment, type TaskStatus } from '@/api/tasks'
import { ApiError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { useCountersStore } from '@/stores/counters'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import { dayLabel, hm } from '@/utils/dates'
import { relativeTime } from '@/utils/format'
import type { Locale } from '@/i18n'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const counters = useCountersStore()
const refs = useRefsStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)

const task = ref<Task | null>(null)
const comments = ref<TaskComment[] | null>(null)
const notFound = ref(false)
const text = ref('')
const sending = ref(false)
const moving = ref<TaskStatus | null>(null)
const editOpen = ref(false)
const archiveOpen = ref(false)
const busy = ref(false)

const id = computed(() => Number(route.params.id))
const me = computed(() => auth.user?.id ?? 0)
const isAuthor = computed(() => task.value?.creator_id === me.value || (auth.can('tasks.create', 'branch') && !!task.value))
const moves = computed(() => (task.value ? nextStatuses(task.value, me.value, isAuthor.value) : []))
const link = computed(() => (task.value ? linkRoute(task.value.link_type, task.value.link_id) : null))

async function load() {
  notFound.value = false
  try {
    task.value = await tasksApi.get(id.value)
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 403)) notFound.value = true
    return
  }
  comments.value = await tasksApi.comments(id.value).catch(() => [])
}
watch(id, load, { immediate: true })

async function move(s: TaskStatus) {
  moving.value = s
  try {
    task.value = await tasksApi.patch(id.value, { status: s })
    toast.ok(t('tasks.moved', { s: t(`tasks.status.${s}`) }))
    counters.refresh()
  } catch {
    /* toast */
  } finally {
    moving.value = null
  }
}
async function send() {
  const body = text.value.trim()
  if (!body || sending.value) return
  sending.value = true
  try {
    const r = await tasksApi.comment(id.value, body)
    comments.value = [...(comments.value ?? []), { id: r.id, at: r.at, text: body, author_id: me.value, author: auth.user?.full_name ?? '', file_url: null }]
    text.value = ''
    if (task.value) task.value.comments++
  } finally {
    sending.value = false
  }
}
async function archive() {
  busy.value = true
  try {
    await tasksApi.archive(id.value)
    toast.ok(t('tasks.archived'))
    counters.refresh()
    router.replace('/tasks')
  } finally {
    busy.value = false
  }
}
const due = (x: Task) => (x.due_at ? `${dayLabel(x.due_at, loc.value, { weekday: 'short', day: 'numeric', month: 'long' })}, ${hm(x.due_at, loc.value)}` : t('tasks.noDue'))
</script>

<template>
  <UiEmptyState v-if="notFound" large icon="task" :title="t('tasks.notFound')" :text="t('notFound.text')"><UiButton to="/tasks" icon="arrow">{{ t('nav.tasks') }}</UiButton></UiEmptyState>
  <div v-else-if="!task" class="card card-pad"><UiSkeleton :lines="6" /></div>
  <template v-else>
    <nav class="crumbs" :aria-label="t('common.breadcrumbs')"><RouterLink to="/tasks">{{ t('nav.tasks') }}</RouterLink> / <span>#{{ task.id }}</span></nav>
    <div class="ph">
      <div>
        <h1 class="task-h">{{ task.title }}</h1>
        <p class="chips-row">
          <UiChip :tone="STATUS_TONE[task.status]">{{ t(`tasks.status.${task.status}`) }}</UiChip>
          <span class="chip"><span class="prio" :class="task.priority" />{{ t(`tasks.priority.${task.priority}`) }}</span>
          <UiChip v-if="task.overdue" tone="red" icon="alert">{{ t('tasks.overdue', { when: relativeTime(task.due_at!, loc) }) }}</UiChip>
          <UiChip v-if="task.recurrence" icon="history">{{ t(`tasks.${task.recurrence}`) }}</UiChip>
        </p>
      </div>
      <span class="sp" />
      <UiButton v-if="task.creator_id === me" icon="edit" @click="editOpen = true">{{ t('common.edit') }}</UiButton>
      <UiButton v-if="auth.can('tasks.create') && task.creator_id === me" variant="ghost" icon="archive" :aria-label="t('tasks.archive')" :title="t('tasks.archive')" @click="archiveOpen = true" />
    </div>

    <div class="grid task-grid">
      <div class="grid" style="align-content: start; grid-template-columns: minmax(0, 1fr)">
        <UiCard :title="t('tasks.description')">
          <p v-if="task.description" class="m0 pre">{{ task.description }}</p>
          <p v-else class="muted m0">{{ t('tasks.noDescription') }}</p>
          <div v-if="moves.length" class="row-acts task-moves">
            <UiButton v-for="s in moves" :key="s" size="sm" :variant="s === 'done' ? 'primary' : s === 'cancelled' ? 'ghost' : 'navy'" :loading="moving === s" @click="move(s)">{{ t(`tasks.to.${s}`) }}</UiButton>
          </div>
        </UiCard>
        <UiCard :title="t('tasks.comments', { n: task.comments })">
          <UiSkeleton v-if="!comments" :lines="3" />
          <div v-else class="cmts">
            <div v-for="c in comments" :key="c.id" class="cmt">
              <UiAvatar :name="c.author" size="sm" />
              <div class="grow"><b>{{ c.author }}</b> <span class="muted">{{ relativeTime(c.at, loc) }}</span><p class="m0 pre">{{ c.text }}</p></div>
            </div>
            <p v-if="!comments.length" class="muted m0">{{ t('tasks.noComments') }}</p>
          </div>
          <form class="cmt-form" @submit.prevent="send">
            <textarea v-model="text" class="inp" rows="2" :placeholder="t('tasks.commentPh')" :aria-label="t('tasks.commentPh')" maxlength="4000" @keydown.enter.ctrl.prevent="send" @keydown.enter.meta.prevent="send" />
            <UiButton type="submit" variant="navy" icon="send" :loading="sending" :disabled="!text.trim()">{{ t('tasks.send') }}</UiButton>
          </form>
        </UiCard>
      </div>
      <UiCard :title="t('tasks.details')">
        <dl class="dl">
          <dt>{{ t('tasks.due') }}</dt><dd :class="{ redc: task.overdue }">{{ due(task) }}</dd>
          <dt>{{ t('tasks.author') }}</dt><dd>{{ task.creator_name ?? '—' }}</dd>
          <dt>{{ t('tasks.assignees') }}</dt><dd><span v-for="a in task.assignees" :key="a.id" class="who2"><UiAvatar :name="a.full_name" size="sm" />{{ a.full_name }}</span></dd>
          <template v-if="task.branch_id"><dt>{{ t('branch.label') }}</dt><dd>{{ refs.branchName(task.branch_id) }}</dd></template>
          <template v-if="link"><dt>{{ t('tasks.linkLabel') }}</dt><dd><RouterLink :to="link" class="rowlink"><UiIcon name="clip" :size="14" /> {{ t(`tasks.link.${task.link_type}`) }}: {{ task.link_title ?? `#${task.link_id}` }}</RouterLink></dd></template>
          <dt>{{ t('tasks.createdAt') }}</dt><dd>{{ relativeTime(task.created_at, loc) }}</dd>
          <template v-if="task.done_at"><dt>{{ t('tasks.doneAt') }}</dt><dd>{{ relativeTime(task.done_at, loc) }}</dd></template>
        </dl>
      </UiCard>
    </div>

    <TaskDrawer v-model:open="editOpen" :task="task" @saved="(x) => (task = x)" />
    <UiPrompt v-model:open="archiveOpen" :title="t('tasks.archiveTitle')" :text="task.title" :confirm-label="t('tasks.archive')" danger :busy="busy" @confirm="archive" />
  </template>
</template>
