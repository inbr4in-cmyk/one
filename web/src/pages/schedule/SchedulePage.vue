<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { UiButton, UiIcon, UiSegmented, UiSkeleton } from '@/components/ui'
import LessonModal from '@/components/schedule/LessonModal.vue'
import LessonCreateModal from '@/components/schedule/LessonCreateModal.vue'
import { academicsApi, COURSE_KINDS, KIND_ICON, type CourseKind, type Group, type Lesson } from '@/api/academics'
import type { Room } from '@/api/org'
import { useAuthStore } from '@/stores/auth'
import { useBranchStore } from '@/stores/branch'
import { useRefsStore } from '@/stores/refs'
import { useTeachers } from '@/composables/useTeachers'
import { useMediaQuery } from '@/composables/useMediaQuery'
import { addDays, dayLabel, hm, hoursOf, isoDate, sameDay, weekStart } from '@/utils/dates'
import { tone } from '@/utils/levels'
import type { Locale } from '@/i18n'

type View = 'rooms' | 'teachers' | 'groups'
const PX = 56

const { t, locale } = useI18n()
const route = useRoute()
const auth = useAuthStore()
const branch = useBranchStore()
const refs = useRefsStore()
const loc = computed(() => locale.value as Locale)
const narrow = useMediaQuery('(max-width:820px)')

const start = ref(weekStart(new Date()))
const view = ref<View>(route.query.group ? 'groups' : 'rooms')
/** Selected room / teacher / group id; 0 = all */
const pick = ref<number>(Number(route.query.group) || 0)
const lessons = ref<Lesson[]>([])
const groups = ref<Group[]>([])
const rooms = ref<Room[]>([])
const loading = ref(true)
const selected = ref<Lesson | null>(null)
const creating = ref(false)
const dayIdx = ref((new Date().getDay() + 6) % 7)
const now = ref(new Date())
const timer = setInterval(() => (now.value = new Date()), 60_000)
onBeforeUnmount(() => clearInterval(timer))
const teachers = useTeachers()

/** Course format filter: all, group, duo, individual */
const kind = ref<CourseKind | ''>('')
const kindOf = (l: Lesson): CourseKind => l.kind ?? (l.group_id ? 'group' : 'individual')
const kindOptions = computed(() => [
  { value: '' as const, label: t('kind.all') },
  ...COURSE_KINDS.map((k) => ({ value: k, label: t(`kind.${k}`), icon: KIND_ICON[k] })),
])
const viewOptions = computed(() => [
  { value: 'rooms' as const, label: t('schedule.byRooms') },
  { value: 'teachers' as const, label: t('schedule.byTeachers') },
  { value: 'groups' as const, label: t('schedule.byGroups') },
])

async function load() {
  loading.value = true
  try {
    lessons.value = await academicsApi.lessons({ from: isoDate(start.value), to: isoDate(addDays(start.value, 6)), branch_id: branch.filterId })
  } catch {
    lessons.value = []
  } finally {
    loading.value = false
  }
}
async function loadRefs() {
  groups.value = await academicsApi.groups({ branch_id: branch.filterId }).catch(() => [])
  await refs.load()
  const ids = branch.filterId ? [branch.filterId] : branch.options.filter((o) => o.id !== null).map((o) => o.id as number)
  rooms.value = (await Promise.all(ids.map((id) => refs.roomsOf(id)))).flat()
}
watch(start, load)
watch(() => branch.filterId, () => {
  pick.value = 0
  load()
  loadRefs()
})
watch(view, () => (pick.value = 0))
onMounted(() => {
  load()
  loadRefs()
})

/* Filter chips for the current view, with the week's load */
const chips = computed(() => {
  const count = (fn: (l: Lesson) => boolean) => lessons.value.filter(fn).length
  if (view.value === 'rooms') {
    const many = new Set(rooms.value.map((r) => r.branch_id)).size > 1
    return rooms.value.map((r) => ({ id: r.id, name: many ? `${r.name} · ${refs.branchName(r.branch_id)}` : r.name, n: count((l) => l.room_id === r.id), icon: 'door' }))
  }
  if (view.value === 'teachers') return teachers.value.map((x) => ({ id: x.id, name: x.name, n: count((l) => (l.actual_teacher_id ?? l.teacher_id) === x.id), icon: 'user' }))
  return groups.value.filter((g) => !kind.value || (g.kind ?? 'group') === kind.value)
    .map((g) => ({ id: g.id, name: g.name, n: count((l) => l.group_id === g.id), icon: KIND_ICON[g.kind ?? 'group'] }))
})
const shown = computed(() => {
  const base = kind.value ? lessons.value.filter((l) => kindOf(l) === kind.value) : lessons.value
  if (!pick.value) return base
  if (view.value === 'rooms') return base.filter((l) => l.room_id === pick.value)
  if (view.value === 'teachers') return base.filter((l) => (l.actual_teacher_id ?? l.teacher_id) === pick.value)
  return base.filter((l) => l.group_id === pick.value)
})

/* Conflicts: same room or same teacher at overlapping times (should not happen; flagged loudly if it does) */
const conflicts = computed(() => {
  const out = new Map<number, string[]>()
  const live = lessons.value.filter((l) => l.status !== 'cancelled')
  for (let i = 0; i < live.length; i++) {
    for (let j = i + 1; j < live.length; j++) {
      const a = live[i]!
      const b = live[j]!
      if (!(new Date(a.starts_at) < new Date(b.ends_at) && new Date(b.starts_at) < new Date(a.ends_at))) continue
      const why = a.room_id === b.room_id ? t('schedule.roomBusy', { room: a.room_name ?? '' })
        : (a.actual_teacher_id ?? a.teacher_id) === (b.actual_teacher_id ?? b.teacher_id) ? t('schedule.teacherBusy', { name: a.teacher_name ?? '' }) : null
      if (!why) continue
      out.set(a.id, [...(out.get(a.id) ?? []), `${why}: ${b.group_name ?? ''} ${hm(b.starts_at, loc.value)}`])
      out.set(b.id, [...(out.get(b.id) ?? []), `${why}: ${a.group_name ?? ''} ${hm(a.starts_at, loc.value)}`])
    }
  }
  return out
})

const days = computed(() => {
  const list = Array.from({ length: 7 }, (_, i) => addDays(start.value, i))
  const hasSunday = shown.value.some((l) => new Date(l.starts_at).getDay() === 0)
  return hasSunday ? list : list.slice(0, 6)
})
const hours = computed(() => {
  if (!shown.value.length) return { h0: 9, h1: 21 }
  let h0 = 24
  let h1 = 0
  for (const l of shown.value) {
    h0 = Math.min(h0, Math.floor(hoursOf(l.starts_at)))
    h1 = Math.max(h1, Math.ceil(hoursOf(l.ends_at)))
  }
  // Keep at least 6 rows so a short day still reads as a timetable
  if (h1 - h0 < 6) h1 = Math.min(24, h0 + 6)
  return { h0: Math.max(0, h0), h1 }
})

interface Placed { l: Lesson; top: number; height: number; lane: number; lanes: number }
/** Lessons of one day, laid out in side-by-side lanes when they overlap. */
function placed(d: Date): Placed[] {
  const list = shown.value.filter((l) => sameDay(new Date(l.starts_at), d)).sort((a, b) => a.starts_at.localeCompare(b.starts_at))
  const out: Placed[] = []
  let cluster: Placed[] = []
  let clusterEnd = 0
  const flush = () => {
    const n = Math.max(...cluster.map((p) => p.lane)) + 1
    cluster.forEach((p) => (p.lanes = n))
    cluster = []
  }
  for (const l of list) {
    const s = new Date(l.starts_at).getTime()
    const e = new Date(l.ends_at).getTime()
    if (cluster.length && s >= clusterEnd) flush()
    const used = new Set(cluster.filter((p) => new Date(p.l.ends_at).getTime() > s).map((p) => p.lane))
    let lane = 0
    while (used.has(lane)) lane++
    const p = { l, top: (hoursOf(l.starts_at) - hours.value.h0) * PX + 2, height: Math.max(22, (hoursOf(l.ends_at) - hoursOf(l.starts_at)) * PX - 4), lane, lanes: 1 }
    cluster.push(p)
    out.push(p)
    clusterEnd = Math.max(clusterEnd, e)
  }
  if (cluster.length) flush()
  return out
}
const columns = computed(() => days.value.map((d) => ({ d, items: placed(d) })))
const nowTop = computed(() => (hoursOf(now.value) - hours.value.h0) * PX)
const nowVisible = computed(() => nowTop.value > 0 && nowTop.value < (hours.value.h1 - hours.value.h0) * PX)

const levelColor = (l: Lesson) => tone(refs.level(l.level_id)?.color)
const range = computed(() => {
  const a = days.value[0]!
  const b = days.value[days.value.length - 1]!
  return `${a.toLocaleDateString(loc.value === 'kk' ? 'kk-KZ' : 'ru-RU', { day: 'numeric' })}–${dayLabel(b, loc.value, { day: 'numeric', month: 'long', year: 'numeric' })}`
})
const isThisWeek = computed(() => sameDay(start.value, weekStart(new Date())))
const legend = computed(() => {
  const seen = new Map<number, string>()
  lessons.value.forEach((l) => l.level_id && seen.set(l.level_id, refs.level(l.level_id)?.code ?? ''))
  return [...seen].map(([id, code]) => ({ id, code, c: tone(refs.level(id)?.color) }))
})
const dayLessons = computed(() => columns.value[Math.min(dayIdx.value, columns.value.length - 1)]?.items.map((p) => p.l) ?? [])
const nConflicts = computed(() => shown.value.filter((l) => conflicts.value.has(l.id)).length)
</script>

<template>
  <div class="ph">
    <div><h1>{{ t('schedule.title') }}</h1><p>{{ branch.current.id ? branch.current.name : t('branch.all') }} · {{ range }}</p></div>
    <span class="sp" />
    <UiSegmented v-model="view" :options="viewOptions" :label="t('schedule.view')" size="sm" />
    <UiButton v-if="auth.can('schedule.create')" variant="primary" icon="plus" @click="creating = true">{{ t('schedule.lesson') }}</UiButton>
  </div>

  <div class="toolbar" style="justify-content: space-between">
    <div class="week-nav">
      <UiButton size="sm" icon="arrow" class="flip" :aria-label="t('schedule.prevWeek')" @click="start = addDays(start, -7)" />
      <UiButton size="sm" :disabled="isThisWeek" @click="start = weekStart(new Date())">{{ t('schedule.thisWeek') }}</UiButton>
      <UiButton size="sm" icon="arrow" :aria-label="t('schedule.nextWeek')" @click="start = addDays(start, 7)" />
    </div>
    <UiSegmented v-model="kind" :options="kindOptions" :label="t('kind.label')" size="sm" class="wrap" />
    <div class="legend">
      <span v-for="lv in legend" :key="lv.id" class="lv" :style="{ '--c': lv.c }">{{ lv.code }}</span>
      <span class="lv" style="--c: var(--red)">{{ t('schedule.trial') }}</span>
    </div>
  </div>
  <div class="rooms">
    <button type="button" :class="{ on: pick === 0 }" @click="pick = 0">{{ t('schedule.all') }}<span class="ld">{{ lessons.length }}</span></button>
    <button v-for="c in chips" :key="c.id" type="button" :class="{ on: pick === c.id }" @click="pick = c.id">
      <UiIcon :name="c.icon" :size="16" />{{ c.name }}<span class="ld">{{ c.n }}</span>
    </button>
  </div>

  <div v-if="nConflicts" class="alert red" role="alert" style="margin-top: 12px">
    <UiIcon name="alert" :size="24" /><div class="grow"><b>{{ t('schedule.conflictsN', { n: nConflicts }) }}</b><span>{{ t('schedule.conflictsText') }}</span></div>
  </div>

  <!-- Phone: one day as a list -->
  <template v-if="narrow">
    <div class="day-tabs" role="tablist">
      <button v-for="(c, i) in columns" :key="i" type="button" role="tab" :aria-selected="dayIdx === i" :class="{ today: sameDay(c.d, now) }" @click="dayIdx = i">
        {{ dayLabel(c.d, loc, { weekday: 'short' }) }}<b class="num">{{ c.d.getDate() }}</b><i v-if="c.items.length" />
      </button>
    </div>
    <div class="card">
      <div v-if="loading" style="padding: 16px"><UiSkeleton :lines="4" /></div>
      <TransitionGroup v-else name="fade" tag="div">
        <button v-for="l in dayLessons" :key="l.id" type="button" class="agenda" :class="{ conflict: conflicts.has(l.id), 'has-trial': l.trials }" :style="{ '--c': levelColor(l) }" @click="selected = l">
          <span class="tm num">{{ hm(l.starts_at, loc) }}<small>{{ hm(l.ends_at, loc) }}</small></span>
          <span class="grow"><b><UiIcon :name="KIND_ICON[kindOf(l)]" :size="14" class="kind-ico" :label="t(`kind.${kindOf(l)}`)" />{{ l.group_name ?? t('schedule.individual') }}</b><small>{{ l.room_name }} · {{ l.teacher_name }}<template v-if="l.actual_teacher_id"> · {{ t('schedule.sub') }}</template></small></span>
          <span v-if="conflicts.has(l.id)" class="chip red xs">{{ t('schedule.conflictShort') }}</span>
          <span v-else-if="l.trials" class="chip red xs">{{ t('schedule.trial') }}</span>
        </button>
        <p v-if="!dayLessons.length" key="none" class="muted" style="padding: 18px; margin: 0">{{ t('schedule.noLessonsDay') }}</p>
      </TransitionGroup>
    </div>
  </template>

  <!-- Desktop: week grid -->
  <div v-else class="card sched-wrap scroll-x" style="margin-top: 12px">
    <div class="sched" :style="{ gridTemplateColumns: `60px repeat(${days.length}, minmax(130px, 1fr))` }" :aria-busy="loading">
      <div class="dh" style="padding: 0" />
      <div v-for="c in columns" :key="c.d.toISOString()" class="dh" :class="{ today: sameDay(c.d, now) }">
        {{ dayLabel(c.d, loc, { weekday: 'short' }) }}<span>{{ dayLabel(c.d, loc, { day: 'numeric', month: 'short' }) }}<template v-if="sameDay(c.d, now)"> · {{ t('schedule.today') }}</template></span>
      </div>
      <div class="tc"><div v-for="h in hours.h1 - hours.h0" :key="h" class="hr">{{ hours.h0 + h - 1 }}:00</div></div>
      <div v-for="c in columns" :key="`c${c.d.toISOString()}`" class="day-col">
        <div v-for="h in hours.h1 - hours.h0" :key="h" class="hr" />
        <button
          v-for="p in c.items" :key="p.l.id" type="button" class="blk"
          :class="{ 'has-trial': p.l.trials, conflict: conflicts.has(p.l.id), cancelled: p.l.status === 'cancelled', marked: p.l.attendance_marked_at }"
          :style="{ '--c': levelColor(p.l), top: `${p.top}px`, height: `${p.height}px`, left: `calc(${(p.lane / p.lanes) * 100}% + 4px)`, width: `calc(${100 / p.lanes}% - 8px)`, right: 'auto' }"
          :title="conflicts.get(p.l.id)?.join('\n')"
          @click="selected = p.l"
        >
          <b><UiIcon :name="KIND_ICON[kindOf(p.l)]" :size="11" class="kind-ico" :label="t(`kind.${kindOf(p.l)}`)" />{{ p.l.group_name ?? t('schedule.individual') }}</b>
          <span>{{ hm(p.l.starts_at, loc) }}–{{ hm(p.l.ends_at, loc) }} · {{ p.l.teacher_name }}</span>
          <span>{{ view === 'rooms' && pick ? (p.l.actual_teacher_id ? t('schedule.sub') : '') : p.l.room_name }}</span>
          <span v-if="conflicts.has(p.l.id)" class="trial conf"><UiIcon name="alert" :size="11" />{{ t('schedule.conflictShort') }}</span>
          <span v-else-if="p.l.trials" class="trial"><UiIcon name="flag" :size="11" />{{ t('schedule.trial') }}</span>
        </button>
        <div v-if="sameDay(c.d, now) && nowVisible" class="nowline" :style="{ top: `${nowTop}px` }" />
      </div>
    </div>
  </div>

  <LessonModal :lesson="selected" :teachers="teachers" :conflicts="selected ? conflicts.get(selected.id) ?? [] : []" @close="selected = null" @changed="load" />
  <LessonCreateModal v-model:open="creating" :groups="groups" :teachers="teachers" :room-id="view === 'rooms' ? pick || null : null" @created="load" />
</template>

<style scoped>
.kind-ico { display: inline-block; vertical-align: -2px; margin-right: 4px; opacity: 0.85 }
</style>
