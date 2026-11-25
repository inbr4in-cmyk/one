<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiAvatar, UiIcon, UiInput, UiSegmented, UiSelect, UiSkeleton } from '@/components/ui'
import TaskDoneModal from './TaskDoneModal.vue'
import { leadTasksApi, type LeadTask, type TaskBoard } from '@/api/crm'
import { useAuthStore } from '@/stores/auth'
import { useBranchStore } from '@/stores/branch'
import { keptRef } from '@/utils/kept'
import { nowMs } from '@/utils/clock'
import { addDays, dayLabel, hm, isoDate, schoolIso, schoolNow, toSchool } from '@/utils/dates'
import { tone } from '@/utils/levels'
import type { Locale } from '@/i18n'

/** Tasks on leads as a board by day: leads with no task, overdue, today, tomorrow, later, done today. */
const emit = defineEmits<{ open: [number] }>()
const { t, locale } = useI18n()
const loc = computed(() => locale.value as Locale)
const auth = useAuthStore()
const branch = useBranchStore()
const box = keptRef<'mine' | 'all'>('crm.tasks.box', () => 'mine')
const who = ref(0)
const q = ref('')
const data = ref<TaskBoard | null>(null)
const closing = ref<LeadTask | null>(null)
const dragId = ref<number | null>(null)
const dropKey = ref<string | null>(null)
let seq = 0
let timer: ReturnType<typeof setTimeout> | undefined

async function load() {
  const my = ++seq
  const r = await leadTasksApi.board({ box: box.value, branch_id: branch.filterId, user_id: box.value === 'all' ? who.value || null : null, q: q.value.trim() || undefined }).catch(() => null)
  if (my === seq && r) data.value = r
}
watch([box, who, () => branch.filterId], load)
watch(q, () => {
  clearTimeout(timer)
  timer = setTimeout(load, 300)
})
onMounted(load)
defineExpose({ load })

type Key = 'overdue' | 'today' | 'tomorrow' | 'later'
const day = (n: number) => isoDate(addDays(schoolNow(), n))
function keyOf(x: LeadTask): Key {
  if (!x.due_at) return 'later'
  if (new Date(x.due_at).getTime() < nowMs()) return 'overdue'
  const d = isoDate(toSchool(x.due_at))
  return d <= day(0) ? 'today' : d === day(1) ? 'tomorrow' : 'later'
}
const cols = computed(() => {
  const g: Record<Key, LeadTask[]> = { overdue: [], today: [], tomorrow: [], later: [] }
  for (const x of data.value?.tasks ?? []) g[keyOf(x)].push(x)
  return (['overdue', 'today', 'tomorrow', 'later'] as Key[]).map((k) => ({ k, items: g[k] }))
})
const canEdit = computed(() => auth.can('crm.edit'))
const people = computed(() => [{ value: 0, label: t('crm.allOwners') }, ...(data.value?.people ?? []).map((p) => ({ value: p.id, label: p.full_name }))])
const when = (x: LeadTask) => (x.due_at ? (keyOf(x) === 'today' || keyOf(x) === 'tomorrow' ? hm(x.due_at, loc.value) : `${dayLabel(x.due_at, loc.value, { day: 'numeric', month: 'short' })}, ${hm(x.due_at, loc.value)}`) : '')

/** Dragging a task to another day moves it there, at the same hour. */
const canDrop = (k: string) => k === 'today' || k === 'tomorrow' || k === 'later'
async function onDrop(k: Key) {
  const id = dragId.value
  dragId.value = dropKey.value = null
  const x = data.value?.tasks.find((i) => i.id === id)
  if (!x || !canDrop(k) || keyOf(x) === k) return
  const at = x.due_at ? toSchool(x.due_at) : schoolNow()
  let time = `${String(at.getHours()).padStart(2, '0')}:${String(at.getMinutes()).padStart(2, '0')}`
  const date = day(k === 'today' ? 0 : k === 'tomorrow' ? 1 : 2)
  if (k === 'today' && new Date(schoolIso(date, time)).getTime() < nowMs()) time = '23:00'
  try {
    const fresh = await leadTasksApi.patch(x.id, { due_at: schoolIso(date, time) })
    Object.assign(x, fresh)
  } catch {
    /* toast shown by the client */
  }
}
</script>

<template>
  <div class="toolbar">
    <UiSegmented v-if="data?.wide" v-model="box" :options="[{ value: 'mine', label: t('nv.lt.mine') }, { value: 'all', label: t('nv.lt.all') }]" :label="t('nv.lt.title')" size="sm" />
    <UiSelect v-if="data?.wide && box === 'all' && people.length > 2" v-model="who" :options="people" :label="t('crm.owner')" />
    <UiInput v-model="q" type="search" icon="search" :placeholder="t('crm.searchPh')" class="tb-search" />
  </div>
  <div class="scroll-x scroll-top">
    <div v-if="!data" class="kanban"><div v-for="i in 5" :key="i" class="col"><UiSkeleton :lines="5" /></div></div>
    <div v-else class="kanban tk">
      <section class="col" :aria-label="t('nv.lt.none')">
        <div class="col-h"><span class="st" style="background: var(--red)" /><b>{{ t('nv.lt.none') }}</b><span class="c">{{ data.no_task_total }}</span></div>
        <div class="col-b">
          <article v-for="l in data.no_task" :key="l.id" class="lead unans" tabindex="0" role="button" @click="emit('open', l.id)" @keydown.enter="emit('open', l.id)">
            <div class="r1"><b>{{ l.full_name }}</b></div>
            <div class="tk-lead"><i :style="{ background: tone(l.stage_color ?? '') }" />{{ l.stage_name }}</div>
            <div class="tk-set"><UiIcon name="plus" :size="14" />{{ t('nv.lt.set') }}</div>
          </article>
        </div>
        <p v-if="!data.no_task.length" class="col-empty">{{ t('nv.lt.noneOk') }}</p>
        <p v-if="data.no_task_total > data.no_task.length" class="col-empty">{{ t('crm.more', { n: data.no_task_total - data.no_task.length }) }}</p>
      </section>
      <section
        v-for="c in cols" :key="c.k" class="col" :class="{ drop: dropKey === c.k && canDrop(c.k), nodrop: dropKey === c.k && !canDrop(c.k) }" :aria-label="t(`nv.lt.col.${c.k}`)"
        @dragover.prevent="dropKey = c.k" @dragleave="dropKey === c.k && (dropKey = null)" @drop.prevent="onDrop(c.k)"
      >
        <div class="col-h"><span class="st" :style="{ background: c.k === 'overdue' ? 'var(--red)' : 'var(--navy-600)' }" /><b>{{ t(`nv.lt.col.${c.k}`) }}</b><span class="c">{{ c.items.length }}</span></div>
        <div class="col-b">
          <article
            v-for="x in c.items" :key="x.id" class="lead" :class="{ unans: c.k === 'overdue', dragging: dragId === x.id }" :draggable="canEdit" tabindex="0" role="button"
            @dragstart="dragId = x.id" @dragend="dragId = dropKey = null" @click="emit('open', x.lead.id)" @keydown.enter="emit('open', x.lead.id)"
          >
            <div class="r1"><b :title="x.title">{{ x.title }}</b><UiAvatar v-if="box === 'all' && x.assignee_name" :name="x.assignee_name" size="sm" :title="x.assignee_name" /></div>
            <div class="tk-lead"><i :style="{ background: tone(x.lead.stage_color ?? '') }" />{{ x.lead.full_name }} · {{ x.lead.stage_name }}</div>
            <div class="r3">
              <span class="wait" :class="{ bad: c.k === 'overdue' }"><UiIcon :name="x.daily ? 'history' : 'clock'" :size="16" />{{ when(x) }}</span>
              <span class="sp" />
              <button v-if="canEdit" type="button" class="tk-ok" :title="t('nv.lt.done')" :aria-label="t('nv.lt.done')" @click.stop="closing = x"><UiIcon name="ok" :size="16" /></button>
            </div>
          </article>
        </div>
        <p v-if="!c.items.length" class="col-empty">{{ t('crm.emptyCol') }}</p>
      </section>
      <section class="col" :aria-label="t('nv.lt.col.done')">
        <div class="col-h"><span class="st" style="background: var(--green, #1E8E5A)" /><b>{{ t('nv.lt.col.done') }}</b><span class="c">{{ data.done.length }}</span></div>
        <div class="col-b">
          <article v-for="x in data.done" :key="x.id" class="lead tk-done" tabindex="0" role="button" @click="emit('open', x.lead.id)" @keydown.enter="emit('open', x.lead.id)">
            <div class="r1"><b :title="x.title">{{ x.title }}</b><UiAvatar v-if="box === 'all' && x.assignee_name" :name="x.assignee_name" size="sm" :title="x.assignee_name" /></div>
            <div class="tk-lead"><i :style="{ background: tone(x.lead.stage_color ?? '') }" />{{ x.lead.full_name }}</div>
          </article>
        </div>
        <p v-if="!data.done.length" class="col-empty">{{ t('crm.emptyCol') }}</p>
      </section>
    </div>
  </div>
  <TaskDoneModal :task="closing" @close="closing = null" @done="load" />
</template>

<style scoped>
.tk-lead { display: flex; align-items: center; gap: 6px; font-size: 12.5px; color: var(--muted); margin: 4px 0 8px; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis }
.tk-lead i { width: 8px; height: 8px; border-radius: 50%; flex: none }
.tk-set { display: flex; align-items: center; gap: 4px; font-size: 12.5px; font-weight: 600; color: var(--accent-ink) }
.tk-ok { width: 32px; height: 32px; border-radius: 50%; border: 1px solid var(--line); background: var(--surface); color: var(--accent-ink); display: grid; place-items: center; cursor: pointer }
.tk-ok:hover { background: var(--btn-navy); border-color: var(--btn-navy); color: var(--on-accent) }
.tk-done { opacity: .7; cursor: pointer }
.tk-done b { text-decoration: line-through }
</style>
