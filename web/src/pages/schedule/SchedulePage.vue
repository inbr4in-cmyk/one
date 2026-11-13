<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { UiButton, UiIcon, UiSegmented, UiSkeleton } from '@/components/ui'
import LessonModal from '@/components/schedule/LessonModal.vue'
import LessonCreateModal from '@/components/schedule/LessonCreateModal.vue'
import BackfillModal from '@/components/schedule/BackfillModal.vue'
import { academicsApi, COURSE_KINDS, KIND_ICON, type Group, type Lesson, type LessonKind } from '@/api/academics'
import type { Room } from '@/api/org'
import { useAuthStore } from '@/stores/auth'
import { useBranchStore } from '@/stores/branch'
import { useRefsStore } from '@/stores/refs'
import { useTeachers } from '@/composables/useTeachers'
import { useMediaQuery } from '@/composables/useMediaQuery'
import { addDays, dayLabel, hm, hoursOf, isoDate, sameDay, weekStart, schoolNow, toSchool } from '@/utils/dates'
import { tone } from '@/utils/levels'
import type { Locale } from '@/i18n'

type View = 'rooms' | 'teachers' | 'groups'
const PX = 56

const { t, locale } = useI18n()
const route = useRoute()
const auth = useAuthStore()
const backfilling = ref(false)
const branch = useBranchStore()
const refs = useRefsStore()
const loc = computed(() => locale.value as Locale)
const narrow = useMediaQuery('(max-width:820px)')

const start = ref(weekStart(schoolNow()))
const view = ref<View>(route.query.group ? 'groups' : 'rooms')
/** Selected room / teacher / group id; 0 = all */
const pick = ref<number>(Number(route.query.group) || 0)
const lessons = ref<Lesson[]>([])
const groups = ref<Group[]>([])
const rooms = ref<Room[]>([])
const loading = ref(true)
const selected = ref<Lesson | null>(null)
const creating = ref(false)
const slotPick = ref<{ date: string; start: string; end: string; roomId: number | null } | null>(null)
function newAt(d: Date, sl: { from: string; to: string }, roomId: number | null) {
  slotPick.value = { date: isoDate(d), start: sl.from, end: sl.to, roomId }
  creating.value = true
}
const dayIdx = ref((schoolNow().getDay() + 6) % 7)
const now = ref(schoolNow())
const timer = setInterval(() => (now.value = schoolNow()), 60_000)
onBeforeUnmount(() => clearInterval(timer))
const teachers = useTeachers()

/** Course format filter: all, group, duo, individual */
const kind = ref<LessonKind | ''>('')
const titleOf = (l: Lesson) => l.group_name ?? (l.kind === 'support' ? `Support · ${l.topic ?? ''}` : t('schedule.individual'))
const kindOf = (l: Lesson): LessonKind => l.kind ?? (l.group_id ? 'group' : 'individual')
const kindOptions = computed(() => [
  { value: '' as const, label: t('kind.all') },
  ...[...COURSE_KINDS, 'support' as const].map((k) => ({ value: k, label: t(`kind.${k}`), icon: KIND_ICON[k] })),
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
  const hasSunday = shown.value.some((l) => toSchool(l.starts_at).getDay() === 0)
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
  const list = shown.value.filter((l) => sameDay(toSchool(l.starts_at), d)).sort((a, b) => a.starts_at.localeCompare(b.starts_at))
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
/** Desktop: two rows of the week, Mon/Wed/Fri on top and Tue/Thu/Sat(/Sun) below: groups usually meet on 1-3-5 or 2-4-6. */
const weekRows = computed(() => {
  const odd = columns.value.filter((_, i) => i % 2 === 0 && i < 6)
  const even = columns.value.filter((_, i) => i % 2 === 1 || i === 6)
  return [odd, even].filter((r) => r.length)
})
const capacityOf = (l: Lesson) => (l.group_id ? groups.value.find((g) => g.id === l.group_id)?.capacity : undefined)
/** Slot table rows: lessons grouped by their exact start–end time. */
const slotRows = computed(() => weekRows.value.map((row) => {
  const slots = new Map<string, { key: string; from: string; to: string }>()
  const days = row.map((c) => {
    const bySlot = new Map<string, Lesson[]>()
    for (const p of c.items) {
      const from = hm(p.l.starts_at, loc.value)
      const to = hm(p.l.ends_at, loc.value)
      const key = `${from}-${to}`
      slots.set(key, { key, from, to })
      bySlot.set(key, [...(bySlot.get(key) ?? []), p.l])
    }
    return { d: c.d, bySlot }
  })
  const title = row.map((c) => dayLabel(c.d, loc.value, { weekday: 'short' })).join(' · ')
  return { title, days, slots: [...slots.values()].sort((x, y) => x.key.localeCompare(y.key)) }
}))
const membersOf = (l: Lesson) => (l.kind === 'club' || l.kind === 'support' ? undefined : l.group_id ? groups.value.find((g) => g.id === l.group_id)?.members : l.student_id ? 1 : undefined)

const levelColor = (l: Lesson) => tone(refs.level(l.level_id)?.color)
const range = computed(() => {
  const a = days.value[0]!
  const b = days.value[days.value.length - 1]!
  return `${a.toLocaleDateString(loc.value === 'kk' ? 'kk-KZ' : 'ru-RU', { day: 'numeric' })}–${dayLabel(b, loc.value, { day: 'numeric', month: 'long', year: 'numeric' })}`
})
const isThisWeek = computed(() => sameDay(start.value, weekStart(schoolNow())))
const legend = computed(() => {
  const seen = new Map<number, string>()
  lessons.value.forEach((l) => l.level_id && seen.set(l.level_id, refs.level(l.level_id)?.code ?? ''))
  return [...seen].map(([id, code]) => ({ id, code, c: tone(refs.level(id)?.color) }))
})
/** Desktop layout: the week as two tables, or one day with rooms as columns. */
const layout = ref<'week' | 'day'>('week')
const layoutOptions = computed(() => [
  { value: 'week' as const, label: t('schedule.layoutWeek') },
  { value: 'day' as const, label: t('schedule.layoutDayRooms') },
])
const dayRooms = computed(() => {
  const c = columns.value[Math.min(dayIdx.value, columns.value.length - 1)]
  const list = c?.items.map((p) => p.l) ?? []
  // All rooms of the branch, so free rooms are visible too (a picked room narrows it to one).
  const roomMap = new Map<number, string>(rooms.value.filter((r) => !(view.value === 'rooms' && pick.value) || r.id === pick.value).map((r) => [r.id, r.name]))
  const slots = new Map<string, { key: string; from: string; to: string }>()
  const cell = new Map<string, Lesson[]>()
  for (const l of list) {
    roomMap.set(l.room_id, l.room_name ?? '')
    const from = hm(l.starts_at, loc.value)
    const to = hm(l.ends_at, loc.value)
    const key = `${from}-${to}`
    slots.set(key, { key, from, to })
    cell.set(`${key}|${l.room_id}`, [...(cell.get(`${key}|${l.room_id}`) ?? []), l])
  }
  const roomsList = [...roomMap].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }))
  return { rooms: roomsList, slots: [...slots.values()].sort((a, b) => a.key.localeCompare(b.key)), cell }
})
const dayLessons = computed(() => columns.value[Math.min(dayIdx.value, columns.value.length - 1)]?.items.map((p) => p.l) ?? [])
const nConflicts = computed(() => shown.value.filter((l) => conflicts.value.has(l.id)).length)
</script>

<template>
  <div class="ph">
    <div><h1>{{ t('schedule.title') }}</h1><p>{{ branch.current.id ? branch.current.name : t('branch.all') }} · {{ range }}</p></div>
    <span class="sp" />
    <UiSegmented v-model="view" :options="viewOptions" :label="t('schedule.view')" size="sm" />
    <UiButton v-if="auth.can('students.archive')" @click="backfilling = true">{{ t('schedule.backfill.button') }}</UiButton>
    <UiButton v-if="auth.can('schedule.create')" variant="primary" icon="plus" @click="creating = true">{{ t('schedule.lesson') }}</UiButton>
  </div>

  <div class="toolbar" style="justify-content: space-between">
    <div class="week-nav">
      <UiButton size="sm" icon="arrow" class="flip" :aria-label="t('schedule.prevWeek')" @click="start = addDays(start, -7)" />
      <UiButton size="sm" :disabled="isThisWeek" @click="start = weekStart(schoolNow())">{{ t('schedule.thisWeek') }}</UiButton>
      <UiButton size="sm" icon="arrow" :aria-label="t('schedule.nextWeek')" @click="start = addDays(start, 7)" />
    </div>
    <UiSegmented v-if="!narrow" v-model="layout" :options="layoutOptions" :label="t('schedule.layout')" size="sm" />
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
          <span class="grow"><b><UiIcon :name="KIND_ICON[kindOf(l)]" :size="14" class="kind-ico" :label="t(`kind.${kindOf(l)}`)" />{{ titleOf(l) }}<span v-if="membersOf(l) !== undefined" class="mem" :title="t('schedule.members', { n: membersOf(l) })"><UiIcon name="users" :size="14" />{{ membersOf(l) }}</span></b><small>{{ l.room_name }} · {{ l.teacher_name }}<template v-if="l.actual_teacher_id"> · {{ t('schedule.sub') }}</template></small></span>
          <span v-if="conflicts.has(l.id)" class="chip red xs">{{ t('schedule.conflictShort') }}</span>
          <span v-else-if="l.trials" class="chip red xs">{{ t('schedule.trial') }}</span>
        </button>
        <p v-if="!dayLessons.length" key="none" class="muted" style="padding: 18px; margin: 0">{{ t('schedule.noLessonsDay') }}</p>
      </TransitionGroup>
    </div>
  </template>

  <!-- Desktop: two tables (Mon/Wed/Fri, Tue/Thu/Sat): time slots as rows, days as columns, lessons stacked in full -->
  <template v-if="!narrow && layout === 'day'">
    <div class="day-tabs" role="tablist">
      <button v-for="(c, i) in columns" :key="i" type="button" role="tab" :aria-selected="dayIdx === i" :class="{ today: sameDay(c.d, now) }" @click="dayIdx = i">
        {{ dayLabel(c.d, loc, { weekday: 'short' }) }}<b class="num">{{ c.d.getDate() }}</b><i v-if="c.items.length" />
      </button>
    </div>
    <div v-if="loading" class="card" style="padding: 16px"><UiSkeleton :lines="6" /></div>
    <section v-else class="card wk">
      <div class="scroll-x">
        <table class="wk-t" :style="{ minWidth: `${72 + dayRooms.rooms.length * 170}px` }">
          <thead><tr><th class="wk-time" /><th v-for="r in dayRooms.rooms" :key="r.id">{{ r.name }}</th></tr></thead>
          <tbody>
            <tr v-for="sl in dayRooms.slots" :key="sl.key">
              <td class="wk-time"><b>{{ sl.from }}</b><small>{{ sl.to }}</small></td>
              <td v-for="r in dayRooms.rooms" :key="r.id">
                <button
                  v-for="l in dayRooms.cell.get(`${sl.key}|${r.id}`) ?? []" :key="l.id" type="button" class="wl"
                  :class="{ 'has-trial': l.trials, conflict: conflicts.has(l.id), cancelled: l.status === 'cancelled', marked: l.attendance_marked_at }"
                  :style="{ '--c': levelColor(l) }" @click="selected = l"
                >
                  <b><UiIcon :name="KIND_ICON[kindOf(l)]" :size="14" class="kind-ico" :label="t(`kind.${kindOf(l)}`)" />{{ titleOf(l) }}</b>
                  <span v-if="membersOf(l) !== undefined" class="wl-n">{{ membersOf(l) }}<template v-if="capacityOf(l)">/{{ capacityOf(l) }}</template></span>
                  <small>{{ l.teacher_name }}<template v-if="l.actual_teacher_id"> · {{ t('schedule.sub') }}</template></small>
                </button>
                <button v-if="auth.can('schedule.create') && columns[dayIdx]" type="button" class="wl-add" :aria-label="t('schedule.addHere')" :title="t('schedule.addHere')" @click="newAt(columns[dayIdx]!.d, sl, r.id)">+</button>
              </td>
            </tr>
            <tr v-if="!dayRooms.slots.length"><td class="muted" style="padding: 16px">{{ t('schedule.noLessonsDay') }}</td></tr>
          </tbody>
        </table>
      </div>
    </section>
  </template>

  <template v-else-if="!narrow">
    <div v-if="loading" class="card" style="margin-top: 12px; padding: 16px"><UiSkeleton :lines="6" /></div>
    <section v-for="(r, ri) in loading ? [] : slotRows" :key="ri" class="card wk" style="margin-top: 12px">
      <div class="wk-title">{{ r.title }}</div>
      <div class="scroll-x">
        <table class="wk-t">
          <thead>
            <tr>
              <th class="wk-time" />
              <th v-for="c in r.days" :key="c.d.toISOString()" :class="{ today: sameDay(c.d, now) }">
                {{ dayLabel(c.d, loc, { weekday: 'short' }) }} {{ dayLabel(c.d, loc, { day: 'numeric', month: 'short' }) }}<template v-if="sameDay(c.d, now)"> · {{ t('schedule.today') }}</template>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="sl in r.slots" :key="sl.key">
              <td class="wk-time"><b>{{ sl.from }}</b><small>{{ sl.to }}</small></td>
              <td v-for="c in r.days" :key="c.d.toISOString()">
                <button
                  v-for="l in c.bySlot.get(sl.key) ?? []" :key="l.id" type="button" class="wl"
                  :class="{ 'has-trial': l.trials, conflict: conflicts.has(l.id), cancelled: l.status === 'cancelled', marked: l.attendance_marked_at }"
                  :style="{ '--c': levelColor(l) }" :title="conflicts.get(l.id)?.join('\n')" @click="selected = l"
                >
                  <b><UiIcon :name="KIND_ICON[kindOf(l)]" :size="14" class="kind-ico" :label="t(`kind.${kindOf(l)}`)" />{{ titleOf(l) }}</b>
                  <span v-if="membersOf(l) !== undefined" class="wl-n" :title="t('schedule.members', { n: membersOf(l) })">{{ membersOf(l) }}<template v-if="capacityOf(l)">/{{ capacityOf(l) }}</template></span>
                  <small>{{ l.room_name }} · {{ l.teacher_name }}<template v-if="l.actual_teacher_id"> · {{ t('schedule.sub') }}</template></small>
                  <span v-if="conflicts.has(l.id)" class="chip red xs">{{ t('schedule.conflictShort') }}</span>
                  <span v-else-if="l.trials" class="chip red xs">{{ t('schedule.trial') }}</span>
                </button>
                <button v-if="auth.can('schedule.create')" type="button" class="wl-add" :aria-label="t('schedule.addHere')" :title="t('schedule.addHere')" @click="newAt(c.d, sl, null)">+</button>
              </td>
            </tr>
            <tr v-if="!r.slots.length"><td :colspan="r.days.length + 1" class="muted" style="padding: 16px">{{ t('schedule.noLessonsDay') }}</td></tr>
          </tbody>
        </table>
      </div>
    </section>
  </template>

  <LessonModal :lesson="selected" :teachers="teachers" :conflicts="selected ? conflicts.get(selected.id) ?? [] : []" @close="selected = null" @changed="load" />
  <LessonCreateModal v-model:open="creating" :groups="groups" :teachers="teachers" :room-id="slotPick?.roomId ?? (view === 'rooms' ? pick || null : null)" :date="slotPick?.date" :start="slotPick?.start" :end="slotPick?.end" :branch-id="branch.filterId ?? null" @created="load" @update:open="(v: boolean) => !v && (slotPick = null)" />
  <BackfillModal v-if="backfilling" v-model:open="backfilling" :branch-id="branch.filterId ?? null" @done="load()" />
</template>

<style scoped>
.kind-ico { display: inline-block; vertical-align: -2px; margin-right: 4px; opacity: 0.85 }
.wk { padding: 0; overflow: hidden }
.wk-title { padding: 10px 16px; font-weight: 700; color: var(--accent-ink); background: var(--navy-50); border-bottom: 1px solid var(--line); text-transform: capitalize }
.wk-t { width: 100%; border-collapse: collapse; table-layout: fixed; min-width: 760px }
.wk-t th { text-align: left; padding: 10px 12px; font-size: 13.5px; font-weight: 600; border-bottom: 1px solid var(--line); text-transform: capitalize }
.wk-t th.today { color: var(--red-ink) }
.wk-t td { vertical-align: top; padding: 8px; border-bottom: 1px solid var(--grid); border-left: 1px solid var(--grid) }
.wk-t tr:last-child td { border-bottom: 0 }
.wk-t .wk-time { width: 72px; border-left: 0; font-size: 13px }
.wk-t td.wk-time small { display: block; color: var(--muted) }
.wl { position: relative; display: block; width: 100%; text-align: left; font: inherit; font-size: 13px; color: inherit; cursor: pointer; border: 0; border-left: 3px solid var(--c); border-radius: 8px; padding: 6px 54px 6px 10px; margin-bottom: 6px; background: color-mix(in srgb, var(--c) 10%, var(--surface)); transition: background var(--t-fast) var(--ease-out) }
.wl:last-child { margin-bottom: 0 }
.wl:hover { background: color-mix(in srgb, var(--c) 18%, var(--surface)) }
.wl b { display: block; overflow-wrap: anywhere }
.wl small { display: block; color: var(--muted) }
.wl .wl-n { position: absolute; right: 8px; top: 6px; font-size: 12px; font-weight: 700; color: var(--accent-ink); background: var(--surface); border: 1px solid var(--line); border-radius: 999px; padding: 0 7px }
.wl .chip { margin-top: 4px }
.wl.has-trial { outline: 1.5px dashed var(--red); outline-offset: -1.5px }
.wl.conflict { outline: 2px solid var(--red); outline-offset: -2px }
.wl.cancelled { opacity: 0.55; text-decoration: line-through }
.wl.marked::after { content: ""; position: absolute; right: 9px; bottom: 8px; width: 7px; height: 7px; border-radius: 50%; background: var(--ok) }
.mem { display: inline-flex; align-items: center; gap: 2px; margin-left: 6px; font-weight: 600; opacity: 0.8; white-space: nowrap }
.wk-t td { position: relative }
.wl-add { display: block; width: 100%; min-height: 22px; margin-top: 4px; border: 1px dashed var(--line); border-radius: var(--r-sm); background: none; color: var(--muted); cursor: pointer; opacity: 0; transition: opacity var(--t-fast) }
.wk-t td:hover .wl-add, .wl-add:focus-visible { opacity: 1 }
.wl-add:hover { border-color: var(--navy); color: var(--navy) }
</style>
