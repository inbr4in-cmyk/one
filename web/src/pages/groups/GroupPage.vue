<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { UiAvatar, UiButton, UiCard, UiChip, UiEmptyState, UiField, UiIcon, UiInput, UiModal, UiPrompt, UiSelect, UiSkeleton } from '@/components/ui'
import LevelTag from '@/components/students/LevelTag.vue'
import StudentPicker from '@/components/students/StudentPicker.vue'
import GroupFormDrawer from '@/components/schedule/GroupFormDrawer.vue'
import HomeworkDrawer from '@/components/homework/HomeworkDrawer.vue'
import HomeworkModal from '@/components/homework/HomeworkModal.vue'
import { academicsApi, type Group, type GroupMember, type Homework, type Lesson } from '@/api/academics'
import type { Room } from '@/api/org'
import type { StudentListItem } from '@/api/students'
import { ApiError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import { useTeachers } from '@/composables/useTeachers'
import { addDays, dayLabel, dmy, hm, isoDate, weekdayShort } from '@/utils/dates'
import { tone } from '@/utils/levels'
import type { Locale } from '@/i18n'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const refs = useRefsStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)

const g = ref<Group | null>(null)
const notFound = ref(false)
const members = ref<GroupMember[] | null>(null)
const lessons = ref<Lesson[] | null>(null)
const homework = ref<Homework[] | null>(null)
const rooms = ref<Room[]>([])
const modal = ref<'edit' | 'member' | 'rule' | 'hw' | 'archive' | null>(null)
const removing = ref<GroupMember | null>(null)
const endingRule = ref<number | null>(null)
const conflicts = ref<string[]>([])
const allConflicts = ref(false)
const busy = ref(false)
const ruleError = ref<string | null>(null)
const teachers = useTeachers()

const id = computed(() => Number(route.params.id))
const lv = computed(() => refs.level(g.value?.level_id))
const room = computed(() => rooms.value.find((r) => r.id === g.value?.room_id))

async function load() {
  notFound.value = false
  try {
    g.value = await academicsApi.group(id.value)
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 403)) notFound.value = true
    return
  }
  rooms.value = await refs.roomsOf(g.value.branch_id)
  const now = new Date()
  const [m, l, h] = await Promise.all([
    academicsApi.members(id.value).catch(() => []),
    academicsApi.lessons({ from: isoDate(addDays(now, -7)), to: isoDate(addDays(now, 21)), group_id: id.value, include_cancelled: true }).catch(() => []),
    auth.can('homework.view') ? academicsApi.homework(id.value).catch(() => []) : Promise.resolve([]),
  ])
  members.value = m
  lessons.value = l
  homework.value = h
}
watch(id, load, { immediate: true })

const upcoming = computed(() => {
  const now = Date.now()
  return (lessons.value ?? []).filter((l) => new Date(l.ends_at).getTime() >= now - 86400000).slice(0, 8)
})

/* ---- members ---- */
async function addMember(s: StudentListItem) {
  try {
    await academicsApi.addMember(id.value, s.id)
    toast.ok(t('groups.memberAdded', { name: s.full_name }))
    modal.value = null
    load()
  } catch {
    /* toast */
  }
}
async function removeMember() {
  if (!removing.value) return
  busy.value = true
  try {
    await academicsApi.removeMember(id.value, removing.value.student_id)
    toast.ok(t('groups.memberRemoved'))
    removing.value = null
    load()
  } finally {
    busy.value = false
  }
}

/* ---- schedule rules ---- */
const rule = reactive({ weekdays: [] as number[], start: '16:00', end: '17:30', room_id: 0, from: isoDate(new Date()), to: '' })
const roomOptions = computed(() => rooms.value.filter((r) => r.status === 'active').map((r) => ({ value: r.id, label: `${r.name} · ${r.capacity}` })))
function openRule() {
  Object.assign(rule, { weekdays: [], start: '16:00', end: '17:30', room_id: g.value?.room_id ?? roomOptions.value[0]?.value ?? 0, from: isoDate(new Date()), to: '' })
  ruleError.value = null
  modal.value = 'rule'
}
const toggleDay = (d: number) => (rule.weekdays = rule.weekdays.includes(d) ? rule.weekdays.filter((x) => x !== d) : [...rule.weekdays, d].sort())
async function addRule() {
  ruleError.value = !rule.weekdays.length ? t('groups.rule.daysRequired') : rule.end <= rule.start ? t('groups.rule.badTime') : !rule.room_id ? t('groups.rule.roomRequired') : null
  if (ruleError.value) return
  busy.value = true
  try {
    const r = await academicsApi.addRule(id.value, { weekdays: rule.weekdays, start_time: rule.start, end_time: rule.end, room_id: rule.room_id, valid_from: rule.from, valid_to: rule.to || null })
    toast.ok(t('groups.rule.created', { n: r.created }))
    conflicts.value = r.conflicts
    modal.value = null
    load()
  } catch (e) {
    if (e instanceof ApiError) ruleError.value = e.detail
  } finally {
    busy.value = false
  }
}
async function endRule() {
  if (endingRule.value === null) return
  busy.value = true
  try {
    await academicsApi.endRule(endingRule.value)
    toast.ok(t('groups.rule.ended'))
    endingRule.value = null
    load()
  } finally {
    busy.value = false
  }
}

/* ---- homework ---- */
const hwEditing = ref<Homework | null>(null)
const hwOpen = ref<Homework | null>(null)
const hwDrawer = ref(false)
function openHw(h: Homework | null = null) {
  hwEditing.value = h
  modal.value = 'hw'
}
function showHw(h: Homework) {
  hwOpen.value = h
  hwDrawer.value = true
}
async function reloadHw() {
  homework.value = await academicsApi.homework(id.value).catch(() => homework.value)
  if (hwOpen.value) hwOpen.value = homework.value?.find((x) => x.id === hwOpen.value!.id) ?? hwOpen.value
}
function onHwSaved(h: Homework) {
  reloadHw()
  if (hwOpen.value?.id === h.id) hwOpen.value = { ...hwOpen.value, ...h }
}
// Deep link from the attendance sheet: /groups/:id?hw=<homework id>
watch(homework, (list) => {
  const want = Number(route.query.hw)
  const h = want ? list?.find((x) => x.id === want) : null
  if (h) {
    showHw(h)
    router.replace({ query: { ...route.query, hw: undefined } })
  }
})

async function archive() {
  busy.value = true
  try {
    await academicsApi.archiveGroup(id.value)
    toast.ok(t('groups.archived'))
    router.push('/groups')
  } finally {
    busy.value = false
  }
}

const STATUS_TONE = { recruiting: 'info', active: 'ok', finished: undefined } as const
const roomName = (rid: number) => rooms.value.find((r) => r.id === rid)?.name ?? `#${rid}`
const lessonState = (l: Lesson) => (l.status === 'cancelled' ? 'red' : l.attendance_marked_at ? 'ok' : new Date(l.starts_at) <= new Date() ? 'warn' : undefined)
</script>

<template>
  <UiEmptyState v-if="notFound" large icon="groups" :title="t('groups.notFound')" :text="t('notFound.text')">
    <UiButton to="/groups" icon="arrow">{{ t('groups.title') }}</UiButton>
  </UiEmptyState>

  <template v-else-if="!g"><div class="card" style="padding: 20px"><UiSkeleton :lines="4" /></div></template>

  <template v-else>
    <nav class="crumbs" :aria-label="t('common.breadcrumbs')"><RouterLink to="/groups">{{ t('groups.title') }}</RouterLink> / <span>{{ g.name }}</span></nav>
    <div class="card" style="margin-bottom: 16px">
      <div class="stu-head">
        <span class="gav lg" :style="{ '--c': tone(lv?.color) }">{{ g.name.slice(0, 2) }}</span>
        <div style="flex: 1; min-width: 220px">
          <h2>{{ g.name }}<template v-if="lv"> · {{ lv.name }}</template></h2>
          <div class="muted" style="margin-top: 2px">
            {{ g.teacher_name ?? '—' }} · {{ refs.branchName(g.branch_id) }}<template v-if="room"> · {{ room.name }}</template>
            <template v-if="g.starts_on"> · {{ t('groups.from', { date: dmy(g.starts_on, loc) }) }}</template>
          </div>
          <div class="facts">
            <UiChip :tone="STATUS_TONE[g.status]">{{ t(`groups.status.${g.status}`) }}</UiChip>
            <span class="chip">{{ t('groups.seats', { n: g.members, cap: g.capacity }) }}</span>
            <span v-if="lv" class="chip"><LevelTag :id="g.level_id" full /></span>
          </div>
        </div>
        <div class="head-acts">
          <UiButton v-if="auth.can('chats.use') && g.chat_id" icon="chat" :to="`/chats/${g.chat_id}`">{{ t('groups.chat') }}</UiButton>
          <UiButton v-if="auth.can('schedule.edit')" icon="edit" @click="modal = 'edit'">{{ t('common.edit') }}</UiButton>
          <UiButton v-if="auth.can('students.archive')" variant="ghost" danger icon="delete" :aria-label="t('groups.archive')" @click="modal = 'archive'">{{ t('groups.archive') }}</UiButton>
        </div>
      </div>
    </div>

    <div v-if="conflicts.length" class="alert red" role="alert">
      <UiIcon name="alert" :size="24" />
      <div class="grow">
        <b>{{ t('groups.rule.conflicts', { n: conflicts.length }) }}</b>
        <ul class="conf-list"><li v-for="(c, i) in allConflicts ? conflicts : conflicts.slice(0, 5)" :key="i">{{ c }}</li></ul>
        <button v-if="conflicts.length > 5" type="button" class="linkbtn" @click="allConflicts = !allConflicts">{{ allConflicts ? t('common.hide') : t('groups.rule.showAll', { n: conflicts.length - 5 }) }}</button>
      </div>
      <UiButton size="sm" variant="ghost" icon="x" :aria-label="t('common.close')" @click="conflicts = []" />
    </div>

    <div class="grid grp-grid stagger">
      <UiCard :title="t('groups.members')" icon="users">
        <template v-if="auth.can('students.edit')" #actions>
          <UiButton v-if="g.kind !== 'club'" size="sm" variant="ghost" icon="plus" :disabled="g.members >= g.capacity" @click="modal = 'member'">{{ t('common.add') }}</UiButton>
        </template>
        <UiSkeleton v-if="!members" :lines="4" />
        <template v-else>
          <div v-for="m in members" :key="m.student_id" class="list-row">
            <UiAvatar :name="m.full_name" size="sm" />
            <div class="grow">
              <RouterLink v-if="auth.can('students.view')" :to="{ name: 'student', params: { id: m.student_id } }" class="rowlink"><b>{{ m.full_name }}</b></RouterLink>
              <b v-else>{{ m.full_name }}</b>
              <span :class="{ warnc: m.lessons_left <= 2 }">{{ t('students.lessonsLeft', { n: m.lessons_left }) }}<template v-if="m.status === 'frozen'"> · {{ t('students.status.frozen') }}</template></span>
            </div>
            <UiButton v-if="auth.can('students.edit')" size="sm" variant="ghost" icon="x" :aria-label="t('groups.removeMember')" @click="removing = m" />
          </div>
          <p v-if="!members.length" class="muted m0">{{ t('groups.noMembers') }}</p>
        </template>
      </UiCard>

      <div class="grid">
        <UiCard :title="t('groups.schedule')" icon="cal">
          <template v-if="auth.can('schedule.create')" #actions>
            <UiButton size="sm" variant="ghost" icon="plus" @click="openRule">{{ t('groups.rule.add') }}</UiButton>
          </template>
          <div v-for="r in g.schedule" :key="r.id" class="list-row">
            <span class="srcico" style="background: var(--navy-600)"><svg><use href="#i-clock" /></svg></span>
            <div class="grow"><b>{{ r.weekdays.map((d) => weekdayShort(d, loc)).join(' / ') }} · {{ r.start.slice(0, 5) }}–{{ r.end.slice(0, 5) }}</b><span>{{ roomName(r.room_id) }}</span></div>
            <UiButton v-if="auth.can('schedule.edit')" size="sm" variant="ghost" icon="x" :aria-label="t('groups.rule.end')" @click="endingRule = r.id" />
          </div>
          <p v-if="!g.schedule.length" class="muted m0">{{ t('groups.noSchedule') }}</p>
        </UiCard>

        <UiCard :title="t('groups.lessons')" icon="clock">
          <template #actions><UiButton size="sm" variant="ghost" :to="{ path: '/schedule', query: { group: g.id } }">{{ t('nav.schedule') }}</UiButton></template>
          <UiSkeleton v-if="!lessons" :lines="3" />
          <template v-else>
            <component :is="auth.can('attendance.view') && l.status !== 'cancelled' ? 'RouterLink' : 'div'" v-for="l in upcoming" :key="l.id" :to="`/attendance/${l.id}`" class="list-row" :class="{ struck: l.status === 'cancelled' }">
              <div class="grow"><b class="num">{{ dayLabel(l.starts_at, loc) }} · {{ hm(l.starts_at, loc) }}–{{ hm(l.ends_at, loc) }}</b><span>{{ l.room_name }}<template v-if="l.actual_teacher_id"> · {{ t('schedule.sub') }}</template><template v-if="l.cancel_reason"> · {{ l.cancel_reason }}</template></span></div>
              <UiChip v-if="lessonState(l)" :tone="lessonState(l)" small>{{ l.status === 'cancelled' ? t('schedule.cancelled') : l.attendance_marked_at ? t('attendance.marked') : t('attendance.notMarked') }}</UiChip>
            </component>
            <p v-if="!upcoming.length" class="muted m0">{{ t('groups.noLessons') }}</p>
          </template>
        </UiCard>

        <UiCard v-if="auth.can('homework.view')" :title="t('groups.hw.title')" icon="homework">
          <template v-if="auth.can('homework.manage')" #actions><UiButton size="sm" variant="ghost" icon="plus" @click="openHw()">{{ t('common.add') }}</UiButton></template>
          <button v-for="h in homework ?? []" :key="h.id" type="button" class="list-row hw-row" @click="showHw(h)">
            <div class="grow"><b>{{ h.title }}</b><span><template v-if="h.due_at">{{ t('groups.hw.due', { date: dmy(h.due_at, loc) }) }} · </template>{{ t('groups.hw.stats', { s: h.submitted, c: h.checked }) }}</span></div>
            <span v-if="h.submitted > h.checked" class="hw-pend" :title="t('hw.f.submitted')">{{ h.submitted - h.checked }}</span>
            <UiIcon name="arrow" :size="16" class="muted" />
          </button>
          <p v-if="homework && !homework.length" class="muted m0">{{ t('groups.hw.empty') }}</p>
        </UiCard>
      </div>
    </div>

    <GroupFormDrawer :open="modal === 'edit'" :group="g" :teachers="teachers" @update:open="(v) => !v && (modal = null)" @saved="(x) => (g = x)" />

    <UiModal :open="modal === 'member'" :title="t('groups.addMember')" @update:open="(v) => !v && (modal = null)">
      <StudentPicker :branch-id="g.branch_id" :exclude="members?.map((m) => m.student_id)" @pick="addMember" />
    </UiModal>

    <UiModal :open="modal === 'rule'" :title="t('groups.rule.add')" @update:open="(v) => !v && (modal = null)">
      <form id="rule-form" class="stack" @submit.prevent="addRule">
        <UiField :label="t('groups.rule.days')">
          <div class="pack-row">
            <button v-for="d in 7" :key="d" type="button" class="tgl" :aria-pressed="rule.weekdays.includes(d - 1)" @click="toggleDay(d - 1)">{{ weekdayShort(d - 1, loc) }}</button>
          </div>
        </UiField>
        <div class="form-2">
          <UiInput v-model="rule.start" type="time" :label="t('groups.rule.start')" />
          <UiInput v-model="rule.end" type="time" :label="t('groups.rule.end2')" />
        </div>
        <UiField :label="t('groups.room')"><UiSelect v-model="rule.room_id" :options="roomOptions" :label="t('groups.room')" block /></UiField>
        <div class="form-2">
          <UiInput v-model="rule.from" type="date" :label="t('groups.rule.from')" />
          <UiInput v-model="rule.to" type="date" :min="rule.from" :label="t('groups.rule.to')" :hint="t('groups.rule.toHint')" />
        </div>
        <p v-if="ruleError" class="form-err m0" role="alert">{{ ruleError }}</p>
      </form>
      <template #footer="{ close }">
        <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
        <UiButton variant="primary" type="submit" form="rule-form" :loading="busy">{{ t('groups.rule.create') }}</UiButton>
      </template>
    </UiModal>

    <HomeworkDrawer v-model:open="hwDrawer" :homework="hwOpen" @edit="openHw" @changed="reloadHw" />
    <HomeworkModal :open="modal === 'hw'" :group-id="g.id" :homework="hwEditing" @update:open="(v) => !v && (modal = null)" @saved="onHwSaved" />

    <UiPrompt :open="removing !== null" :title="t('groups.removeMember')" :text="t('groups.removeText', { name: removing?.full_name ?? '' })" :confirm-label="t('common.remove')" danger :busy="busy" @update:open="(v) => !v && (removing = null)" @confirm="removeMember" />
    <UiPrompt :open="endingRule !== null" :title="t('groups.rule.end')" :text="t('groups.rule.endText')" :confirm-label="t('groups.rule.end')" danger :busy="busy" @update:open="(v) => !v && (endingRule = null)" @confirm="endRule" />
    <UiPrompt :open="modal === 'archive'" :title="t('groups.archive')" :text="t('groups.archiveText', { name: g.name })" :confirm-label="t('groups.archive')" danger :busy="busy" @update:open="(v) => !v && (modal = null)" @confirm="archive" />
  </template>
</template>
