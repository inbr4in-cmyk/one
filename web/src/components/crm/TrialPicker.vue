<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiField, UiInput, UiSegmented, UiSelect, UiSkeleton } from '@/components/ui'
import { crmApi, type TrialSlot } from '@/api/crm'
import { useTeachers } from '@/composables/useTeachers'
import { academicsApi, type Group, type Lesson } from '@/api/academics'
import { addDays, dayLabel, hm, isoDate, sameDay, schoolNow, toSchool, weekStart, weekdayShort } from '@/utils/dates'
import { nowMs } from '@/utils/clock'
import { useRefsStore } from '@/stores/refs'
import type { Locale } from '@/i18n'

/** Trial booking. Group: teacher → that teacher's groups → the group's calendar → a lesson day → save.
 * Individual: teacher → a day → one of the teacher's free windows → a new trial lesson. */
const props = defineProps<{ branchId: number | null; busy?: boolean }>()
const emit = defineEmits<{ pick: [Lesson]; individual: [{ teacher_id: number; branch_id: number; starts_at: string; minutes: number }] }>()
const { t, locale } = useI18n()
const loc = computed(() => locale.value as Locale)
const WEEKS = 5
/** A trial can be entered late: the calendar also shows this many past weeks (a month back). */
const BACK_WEEKS = 4
const calStart = () => addDays(weekStart(schoolNow()), -BACK_WEEKS * 7)
const mode = ref<'group' | 'individual'>('group')
const modeOptions = computed(() => [{ value: 'group' as const, label: t('nv.trial.modeGroup') }, { value: 'individual' as const, label: t('nv.trial.modeIndividual') }])

const groups = ref<Group[] | null>(null)
const teacher = ref(0)
const group = ref<Group | null>(null)
const lessons = ref<Lesson[] | null>(null)
const chosen = ref<Lesson | null>(null)

const refs = useRefsStore()
/** A lead without a branch: the branch is picked first, and the trial then moves the lead there. */
const branch = ref(props.branchId ?? 0)
const branchOptions = computed(() => [{ value: 0, label: t('nv.pickBranch') }, ...refs.branches.map((b) => ({ value: b.id, label: b.name }))])

async function loadGroups() {
  groups.value = null
  teacher.value = 0
  if (!branch.value) {
    groups.value = []
    return
  }
  const id = branch.value
  const list = await academicsApi.groups({ branch_id: id }).catch(() => [])
  if (id !== branch.value) return
  groups.value = list.filter((g) => g.status !== 'finished' && g.kind !== 'individual' && g.kind !== 'duo' && g.kind !== 'club')
}
onMounted(loadGroups)

/* ---------- individual: free windows of a teacher ---------- */
const DAYS = 14
const allTeachers = useTeachers()
const iTeacher = ref(0)
const iTeacherOptions = computed(() => [{ value: 0, label: t('nv.trial.pickTeacher') },
  ...allTeachers.value.filter((x) => !x.branchIds?.length || x.branchIds.includes(branch.value)).map((x) => ({ value: x.id, label: x.name }))])
const minutes = ref(60)
const minuteOptions = computed(() => [30, 45, 60, 90].map((n) => ({ value: n, label: t('nv.trial.minutes', { n }) })))
const days = computed(() => Array.from({ length: DAYS }, (_, i) => addDays(schoolNow(), i)))
const day = ref('')
const minDay = computed(() => isoDate(addDays(schoolNow(), -31)))
const maxDay = computed(() => isoDate(addDays(schoolNow(), 60)))
const slots = ref<TrialSlot[] | null>(null)
const slot = ref<TrialSlot | null>(null)
async function loadSlots() {
  slot.value = null
  slots.value = null
  if (!iTeacher.value || !branch.value || !day.value) return
  const key = `${iTeacher.value}|${branch.value}|${day.value}|${minutes.value}`
  const list = await crmApi.trialSlots(iTeacher.value, branch.value, day.value, minutes.value).catch(() => [])
  if (key === `${iTeacher.value}|${branch.value}|${day.value}|${minutes.value}`) slots.value = list
}
watch([iTeacher, minutes, day], loadSlots)
watch(branch, () => (iTeacher.value = 0))
watch(iTeacher, (v) => v && !day.value && (day.value = isoDate(schoolNow())))
watch(branch, loadGroups)

const teacherOptions = computed(() => {
  const seen = new Map<number, string>()
  for (const g of groups.value ?? []) if (!seen.has(g.teacher_id)) seen.set(g.teacher_id, g.teacher_name ?? `#${g.teacher_id}`)
  return [{ value: 0, label: t('nv.trial.pickTeacher') }, ...[...seen].sort((a, b) => a[1].localeCompare(b[1])).map(([value, label]) => ({ value, label }))]
})
const teacherGroups = computed(() => (groups.value ?? []).filter((g) => g.teacher_id === teacher.value))

watch(teacher, () => {
  group.value = null
  lessons.value = null
  chosen.value = null
})

async function pickGroup(g: Group) {
  group.value = g
  lessons.value = null
  chosen.value = null
  const start = calStart()
  const list = await academicsApi.lessons({ from: isoDate(start), to: isoDate(addDays(start, (BACK_WEEKS + WEEKS) * 7 - 1)), group_id: g.id }).catch(() => [])
  if (group.value?.id !== g.id) return
  const oldest = nowMs() - 31 * 86400000
  lessons.value = list.filter((l) => l.status !== 'cancelled' && new Date(l.starts_at).getTime() > oldest).sort((a, b) => a.starts_at.localeCompare(b.starts_at))
}

/** Four past weeks and five from this Monday; each day carries the group's lessons that can be booked. */
const weeks = computed(() => {
  const start = calStart()
  const today = schoolNow()
  return Array.from({ length: BACK_WEEKS + WEEKS }, (_, w) => Array.from({ length: 7 }, (_, d) => {
    const day = addDays(start, w * 7 + d)
    return { day, past: day < today && !sameDay(day, today), today: sameDay(day, today), lessons: (lessons.value ?? []).filter((l) => sameDay(toSchool(l.starts_at), day)) }
  }))
})
</script>

<template>
  <div class="trial-pick">
    <UiField v-if="!props.branchId" :label="t('branch.label')">
      <UiSelect v-model="branch" :options="branchOptions" :label="t('branch.label')" block />
    </UiField>
    <UiSegmented v-model="mode" :options="modeOptions" :label="t('nv.trial.mode')" size="sm" />
    <template v-if="mode === 'individual'">
      <template v-if="branch">
        <div class="form-2">
          <UiField :label="t('nv.trial.teacher')"><UiSelect v-model="iTeacher" :options="iTeacherOptions" :label="t('nv.trial.teacher')" block /></UiField>
          <UiField :label="t('nv.trial.length')"><UiSelect v-model="minutes" :options="minuteOptions" :label="t('nv.trial.length')" block /></UiField>
        </div>
        <template v-if="iTeacher">
          <UiInput v-model="day" type="date" :min="minDay" :max="maxDay" :label="t('nv.trial.day')" />
          <div class="tp-days">
            <button v-for="d in days" :key="isoDate(d)" type="button" class="tp-dayb" :class="{ sel: day === isoDate(d) }" :aria-pressed="day === isoDate(d)" @click="day = isoDate(d)">
              <span>{{ weekdayShort((d.getDay() + 6) % 7, loc) }}</span><b class="num">{{ d.getDate() }}</b>
            </button>
          </div>
          <b class="tp-h">{{ t('nv.trial.free') }}</b>
          <UiSkeleton v-if="!slots" :lines="2" />
          <p v-else-if="!slots.length" class="muted m0">{{ t('nv.trial.noFree') }}</p>
          <div v-else class="tp-groups">
            <button v-for="x in slots" :key="x.starts_at" type="button" class="tp-slot wide" :class="{ sel: slot?.starts_at === x.starts_at }" :aria-pressed="slot?.starts_at === x.starts_at" @click="slot = x">{{ hm(x.starts_at, loc) }}</button>
          </div>
          <div v-if="slot" class="tp-foot">
            <span class="grow num"><b>{{ dayLabel(slot.starts_at, loc) }} · {{ hm(slot.starts_at, loc) }}–{{ hm(slot.ends_at, loc) }}</b><br /><span class="muted">{{ slot.room_name }}</span></span>
            <UiButton variant="primary" icon="cal" :loading="busy" @click="emit('individual', { teacher_id: iTeacher, branch_id: branch, starts_at: slot.starts_at, minutes })">{{ t('nv.trial.save') }}</UiButton>
          </div>
        </template>
      </template>
    </template>
    <UiSkeleton v-else-if="!groups" :lines="3" />
    <template v-else-if="branch">
      <UiField :label="t('nv.trial.teacher')">
        <UiSelect v-model="teacher" :options="teacherOptions" :label="t('nv.trial.teacher')" block />
      </UiField>
      <template v-if="teacher">
        <b class="tp-h">{{ t('nv.trial.groups') }}</b>
        <div class="tp-groups">
          <button v-for="g in teacherGroups" :key="g.id" type="button" class="tp-group" :class="{ sel: group?.id === g.id }" :aria-pressed="group?.id === g.id" @click="pickGroup(g)">
            <b>{{ g.name }}</b><span>{{ g.members }}/{{ g.capacity }}</span>
          </button>
        </div>
      </template>
      <template v-if="group">
        <b class="tp-h">{{ t('nv.trial.calendar', { group: group.name }) }}</b>
        <UiSkeleton v-if="!lessons" :lines="4" />
        <template v-else>
          <div class="tp-cal" role="grid">
            <div v-for="i in 7" :key="`h${i}`" class="tp-wd">{{ weekdayShort(i - 1, loc) }}</div>
            <template v-for="(week, wi) in weeks" :key="wi">
              <div v-for="c in week" :key="c.day.getTime()" class="tp-day" :class="{ past: c.past, today: c.today, has: c.lessons.length }">
                <span class="num">{{ c.day.getDate() }}</span>
                <button v-for="l in c.lessons" :key="l.id" type="button" class="tp-slot" :class="{ sel: chosen?.id === l.id }" :aria-pressed="chosen?.id === l.id" @click="chosen = l">{{ hm(l.starts_at, loc) }}</button>
              </div>
            </template>
          </div>
          <p v-if="!lessons.length" class="muted m0">{{ t('crm.noLessons') }}</p>
        </template>
        <div v-if="chosen" class="tp-foot">
          <span class="grow num"><b>{{ dayLabel(chosen.starts_at, loc) }} · {{ hm(chosen.starts_at, loc) }}</b><br /><span class="muted">{{ chosen.room_name }} · {{ chosen.teacher_name }}</span></span>
          <UiButton variant="primary" icon="cal" :loading="busy" @click="emit('pick', chosen)">{{ t('nv.trial.save') }}</UiButton>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.trial-pick { gap: 10px }
.tp-h { font-size: 12.5px; color: var(--muted); font-weight: 600 }
.tp-groups { display: flex; flex-wrap: wrap; gap: 6px }
.tp-group { display: flex; gap: 8px; align-items: baseline; border: 1px solid var(--line); background: var(--surface); border-radius: 10px; padding: 7px 10px; font: inherit; cursor: pointer; color: inherit }
.tp-group span { font-size: 12px; color: var(--muted) }
.tp-group.sel { border-color: var(--btn-navy); box-shadow: inset 0 0 0 1px var(--btn-navy) }
.tp-cal { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 4px }
.tp-wd { font-size: 11px; text-align: center; color: var(--muted); text-transform: capitalize }
.tp-day { min-height: 52px; border: 1px solid var(--line); border-radius: 8px; padding: 3px; display: flex; flex-direction: column; gap: 3px; align-items: stretch; font-size: 11.5px; background: var(--surface) }
.tp-day > span { text-align: right; color: var(--muted); padding-right: 2px }
.tp-day.past:not(.has) { opacity: .45 }
.tp-day.past .tp-slot:not(.sel) { background: var(--line); color: inherit }
.tp-day.today > span { color: var(--red-ink); font-weight: 700 }
.tp-slot { border: 0; border-radius: 6px; padding: 4px 0; font: inherit; font-size: 12px; font-weight: 600; cursor: pointer; background: var(--navy-100); color: var(--accent-ink) }
.tp-slot.wide { padding: 7px 12px; font-size: 13px }
.tp-days { display: flex; gap: 4px; overflow-x: auto; padding-bottom: 2px }
.tp-dayb { flex: 0 0 auto; min-width: 42px; display: flex; flex-direction: column; align-items: center; gap: 1px; border: 1px solid var(--line); background: var(--surface); border-radius: 8px; padding: 5px 4px; font: inherit; font-size: 11px; color: inherit; cursor: pointer; text-transform: capitalize }
.tp-dayb b { font-size: 13.5px }
.tp-dayb.sel { border-color: var(--btn-navy); box-shadow: inset 0 0 0 1px var(--btn-navy) }
.tp-slot.sel { background: var(--red); color: #fff }
.tp-foot { display: flex; gap: 10px; align-items: center; border-top: 1px solid var(--line); padding-top: 10px; font-size: 13px }
</style>
