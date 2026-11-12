<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { onBeforeRouteLeave } from 'vue-router'
import { UiAvatar, UiButton, UiChip, UiEmptyState, UiIcon, UiInput, UiSkeleton, UiTextarea } from '@/components/ui'
import { academicsApi, type AttendanceStatus, type Homework, type Roster, type RosterRow } from '@/api/academics'
import HomeworkDrawer from '@/components/homework/HomeworkDrawer.vue'
import HomeworkModal from '@/components/homework/HomeworkModal.vue'
import { ApiError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import { dayLabel, hm } from '@/utils/dates'
import { tone } from '@/utils/levels'
import type { Locale } from '@/i18n'

interface Row extends RosterRow {
  key: string
  open: boolean
}

const MARKS: { k: AttendanceStatus; cls: string; icon: string }[] = [
  { k: 'present', cls: 'p', icon: 'ok' },
  { k: 'absent', cls: 'a', icon: 'x' },
  { k: 'late', cls: 'l', icon: 'clock' },
  { k: 'excused', cls: 'e', icon: 'file' },
]

const { t, locale } = useI18n()
const route = useRoute()
const auth = useAuthStore()
const refs = useRefsStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)

const roster = ref<Roster | null>(null)
const rows = ref<Row[]>([])
const topic = ref('')
const reason = ref('')
const hwTitle = ref('')
/** Homework given at this lesson (the group's list filtered by lesson) */
const lessonHw = ref<Homework[]>([])
const hwModal = ref(false)
const hwEditing = ref<Homework | null>(null)
const hwOpen = ref<Homework | null>(null)
const hwDrawer = ref(false)
const error = ref<string | null>(null)
const notFound = ref(false)
const busy = ref(false)
const dirty = ref(false)
const now = ref(Date.now())
const tick = setInterval(() => (now.value = Date.now()), 30_000)
onBeforeUnmount(() => clearInterval(tick))

const id = computed(() => Number(route.params.lessonId))
const lesson = computed(() => roster.value?.lesson)
const editable = computed(() => !!roster.value?.can_edit && lesson.value?.status !== 'cancelled')
const liveMin = computed(() => {
  const l = lesson.value
  if (!l) return null
  const s = new Date(l.starts_at).getTime()
  return now.value >= s && now.value < new Date(l.ends_at).getTime() ? Math.round((now.value - s) / 60000) : null
})
const counted = computed(() => rows.value.filter((r) => r.status === 'present' || r.status === 'late').length)
const unmarked = computed(() => rows.value.filter((r) => !r.status && !r.frozen).length)
const absentWithParents = computed(() => rows.value.filter((r) => r.status === 'absent' && !r.is_trial).length)

function fill(r: Roster) {
  roster.value = r
  rows.value = r.rows.map((x) => ({ ...x, key: x.student_id ? `s${x.student_id}` : `l${x.lead_id}`, open: false }))
  topic.value = r.lesson.topic ?? ''
  dirty.value = false
}

async function load() {
  notFound.value = false
  error.value = null
  try {
    fill(await academicsApi.roster(id.value))
    loadHw()
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 403)) notFound.value = true
  }
}
async function loadHw() {
  const gid = roster.value?.lesson.group_id
  if (!gid || !auth.can('homework.view')) return
  lessonHw.value = (await academicsApi.homework(gid).catch(() => [])).filter((h) => h.lesson_id === id.value)
  if (hwOpen.value) hwOpen.value = lessonHw.value.find((h) => h.id === hwOpen.value!.id) ?? hwOpen.value
}
function newHw() {
  hwEditing.value = null
  hwModal.value = true
}
function editHw(h: Homework) {
  hwEditing.value = h
  hwModal.value = true
}
function onHwSaved() {
  hwTitle.value = ''
  loadHw()
}
watch(id, load, { immediate: true })

function set(r: Row, k: AttendanceStatus) {
  if (!editable.value || r.frozen) return
  r.status = r.status === k ? null : k
  dirty.value = true
}
function allPresent() {
  rows.value.forEach((r) => !r.frozen && !r.status && (r.status = 'present'))
  dirty.value = true
}
function setGrade(r: Row, g: number) {
  r.grade = r.grade === g ? null : g
  dirty.value = true
}

async function save() {
  error.value = null
  if (roster.value?.needs_reason && reason.value.trim().length < 3) {
    error.value = t('attendance.reasonNeeded')
    return
  }
  const marks = rows.value.filter((r) => r.status).map((r) => ({
    student_id: r.student_id, lead_id: r.lead_id, status: r.status as AttendanceStatus, grade: r.grade, comment: r.comment?.trim() || null, stars: r.stars,
  }))
  if (!marks.length && lesson.value?.kind !== 'support') {
    error.value = t('attendance.nothing')
    return
  }
  busy.value = true
  try {
    fill(await academicsApi.mark(id.value, { marks, reason: reason.value.trim() || null, topic: topic.value.trim() || null }))
    if (hwTitle.value.trim() && lesson.value?.group_id && auth.can('homework.manage')) {
      try {
        await academicsApi.addHomework(lesson.value.group_id, { title: hwTitle.value.trim(), lesson_id: id.value })
        hwTitle.value = ''
        loadHw()
      } catch (e) {
        toast.error(`${t('attendance.hw')}: ${e instanceof ApiError ? e.detail : t('errors.generic')}`)
      }
    }
    reason.value = ''
    toast.ok(t('attendance.saved'))
  } catch (e) {
    if (e instanceof ApiError) error.value = e.detail
  } finally {
    busy.value = false
  }
}

onBeforeRouteLeave(() => (dirty.value && editable.value ? window.confirm(t('attendance.leave')) : true))
</script>

<template>
  <UiEmptyState v-if="notFound" large icon="check" :title="t('attendance.notFound')" :text="t('notFound.text')">
    <UiButton to="/attendance" icon="arrow">{{ t('attendance.title') }}</UiButton>
  </UiEmptyState>
  <div v-else-if="!roster" class="card" style="padding: 20px"><UiSkeleton :lines="6" /></div>

  <template v-else-if="lesson">
    <div class="ph">
      <div>
        <nav class="crumbs" :aria-label="t('common.breadcrumbs')" style="margin: 0 0 6px"><RouterLink to="/attendance">{{ t('attendance.title') }}</RouterLink> / <span>{{ lesson.group_name }}</span></nav>
        <h1>{{ t('attendance.title') }}</h1>
        <p>{{ editable ? (roster.needs_reason ? t('attendance.fixMode') : t('attendance.window')) : t('attendance.closed') }}</p>
      </div>
    </div>

    <div v-if="lesson.status === 'cancelled'" class="alert red"><UiIcon name="alert" :size="24" /><div class="grow"><b>{{ t('schedule.cancelled') }}</b><span>{{ lesson.cancel_reason }}</span></div></div>
    <div v-else-if="!editable" class="alert info"><UiIcon name="lock" :size="24" /><div class="grow"><b>{{ t('attendance.closedTitle') }}</b><span>{{ t('attendance.closedText') }}</span></div></div>
    <div v-else-if="roster.needs_reason" class="alert"><UiIcon name="alert" :size="24" /><div class="grow"><b>{{ t('attendance.fixTitle') }}</b><span>{{ t('attendance.fixText') }}</span></div></div>

    <div class="card">
      <div class="att-head">
        <span class="gav" :style="{ '--c': tone(refs.level(lesson.level_id)?.color) }">{{ (lesson.group_name ?? '·').slice(0, 2) }}</span>
        <div class="grow">
          <b style="font-size: 16px">{{ lesson.group_name ?? (lesson.kind === 'support' ? 'Support · ' + (lesson.topic ?? '') : t('schedule.individual')) }}<template v-if="refs.level(lesson.level_id)"> · {{ refs.level(lesson.level_id)?.name }}</template></b>
          <div class="muted" style="font-size: 13px">{{ dayLabel(lesson.starts_at, loc, { weekday: 'short', day: 'numeric', month: 'long' }) }} · {{ hm(lesson.starts_at, loc) }}–{{ hm(lesson.ends_at, loc) }} · {{ lesson.room_name }} · {{ lesson.teacher_name }}</div>
        </div>
        <UiChip v-if="liveMin !== null" tone="ok" icon="clock">{{ t('attendance.live', { n: liveMin }) }}</UiChip>
        <UiChip v-else-if="lesson.attendance_marked_at" tone="ok" icon="ok">{{ t('attendance.marked') }}</UiChip>
        <UiButton v-if="editable && unmarked" size="sm" icon="ok" @click="allPresent">{{ t('attendance.allPresent') }}</UiButton>
      </div>

      <div v-for="r in rows" :key="r.key" class="att-row" :class="{ trial: r.is_trial, frozen: r.frozen }">
        <div class="who">
          <UiAvatar :name="r.full_name" />
          <div style="min-width: 0">
            <b>
              <RouterLink v-if="r.student_id && auth.can('students.view')" :to="{ name: 'student', params: { id: r.student_id } }" class="rowlink nm" :title="r.full_name">{{ r.full_name }}</RouterLink>
              <span v-else class="nm" :title="r.full_name">{{ r.full_name }}</span>
              <UiChip v-if="r.is_trial" tone="red" small icon="flag">{{ t('schedule.trial') }}</UiChip>
            </b>
            <span v-if="r.frozen" class="sub">{{ t('attendance.frozen') }}</span>
            <span v-else-if="r.blocked" class="sub redc">{{ t('attendance.blocked') }}</span>
            <span v-else-if="r.lessons_left !== null" class="sub" :class="{ warnc: r.lessons_left <= 2 }">{{ t('students.lessonsLeft', { n: r.lessons_left }) }}<template v-if="r.lessons_left <= 2"> · {{ t('attendance.remind') }}</template></span>
            <span v-else class="sub">{{ t('attendance.trialLead') }}</span>
          </div>
        </div>
        <div class="bal">
          <button v-if="!r.is_trial" type="button" class="tgl sm" :aria-expanded="r.open" :disabled="!editable && !r.grade && !r.comment" @click="r.open = !r.open">
            <UiIcon name="grades" :size="16" />{{ r.grade ?? t('attendance.grade') }}
          </button>
        </div>
        <div class="mark" role="group" :aria-label="r.full_name">
          <button v-for="m in MARKS" :key="m.k" type="button" :class="m.cls" :aria-pressed="r.status === m.k" :disabled="!editable || r.frozen" @click="set(r, m.k)">
            <UiIcon :name="m.icon" :size="16" /><span class="t">{{ t(`attendance.s.${m.k}`) }}</span>
          </button>
        </div>
        <div v-if="r.open" class="att-extra">
          <div class="grades" role="group" :aria-label="t('attendance.grade')">
            <button v-for="g in 5" :key="g" type="button" class="tgl sm" :aria-pressed="r.grade === g" :disabled="!editable" @click="setGrade(r, g)">{{ g }}</button>
          </div>
          <input v-model="r.comment" class="inp mini" :placeholder="t('attendance.comment')" :aria-label="t('attendance.comment')" :disabled="!editable" maxlength="500" @input="dirty = true" />
        </div>
      </div>
      <p v-if="!rows.length" class="muted" style="padding: 18px; margin: 0">{{ lesson?.kind === 'support' ? t('attendance.supportNote') : t('groups.noMembers') }}</p>

      <div v-if="lessonHw.length || (!editable && lesson.group_id && auth.can('homework.manage'))" class="att-hw">
        <div class="att-hw-h"><b>{{ t('hw.lessonHw') }}</b><span v-if="!lessonHw.length" class="muted">· {{ t('groups.hw.empty') }}</span><span class="sp" /><RouterLink :to="`/groups/${lesson.group_id}`" class="rowlink" style="font-size: 13px">{{ t('hw.openGroup') }}</RouterLink></div>
        <button v-for="h in lessonHw" :key="h.id" type="button" class="list-row hw-row" @click="hwOpen = h; hwDrawer = true">
          <UiIcon name="homework" :size="18" class="muted" />
          <div class="grow"><b>{{ h.title }}</b><span>{{ t('groups.hw.stats', { s: h.submitted, c: h.checked }) }}</span></div>
          <span v-if="h.submitted > h.checked" class="hw-pend">{{ h.submitted - h.checked }}</span>
          <UiIcon name="arrow" :size="16" class="muted" />
        </button>
        <UiButton v-if="auth.can('homework.manage')" size="sm" variant="ghost" icon="plus" @click="newHw">{{ t('groups.hw.new') }}</UiButton>
      </div>

      <div v-if="editable" class="att-extra-form">
        <UiInput v-model="topic" :label="t('attendance.topic')" :placeholder="t('attendance.topicPh')" @update:model-value="dirty = true" />
        <div v-if="auth.can('homework.manage') && lesson.group_id && !lessonHw.length" class="hw-quick">
          <UiInput v-model="hwTitle" :label="t('attendance.hw')" :placeholder="t('attendance.hwPh')" />
          <UiButton size="sm" variant="ghost" @click="newHw">{{ t('hw.withDetails') }}</UiButton>
        </div>
        <UiTextarea v-if="roster.needs_reason" v-model="reason" :label="t('attendance.reason')" :rows="2" />
      </div>

      <div class="att-foot" :class="{ ro: !editable }">
        <div class="wa-note">
          <span class="srcico wa"><svg><use href="#i-wa" /></svg></span>
          <div><b>{{ t('attendance.waTitle') }}</b><div class="muted" style="font-size: 12.5px">{{ absentWithParents ? t('attendance.waAbsent', { n: absentWithParents }) : t('attendance.waNone') }}</div></div>
        </div>
        <div class="num" style="font-size: 13px; text-align: right">
          <b>{{ t('attendance.present', { n: counted, total: rows.length }) }}</b>
          <div v-if="unmarked" class="muted">{{ t('attendance.unmarked', { n: unmarked }) }}</div>
        </div>
        <UiButton v-if="editable" variant="primary" icon="ok" :loading="busy" @click="save">{{ lesson?.kind === 'support' && !rows.length ? t('attendance.supportDone') : t('common.save') }}</UiButton>
      </div>
      <p v-if="error" class="form-err" role="alert" style="padding: 0 18px 14px; margin: 0">{{ error }}</p>
    </div>
  </template>
  <HomeworkDrawer v-model:open="hwDrawer" :homework="hwOpen" @edit="editHw" @changed="loadHw" />
  <HomeworkModal v-if="lesson?.group_id" v-model:open="hwModal" :group-id="lesson.group_id" :homework="hwEditing" :lesson-id="id" :default-title="hwTitle" @saved="onHwSaved" />
</template>
