<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiField, UiSelect, UiSkeleton } from '@/components/ui'
import { academicsApi, type Group, type Lesson } from '@/api/academics'
import { addDays, dayLabel, hm, isoDate, sameDay, schoolNow, toSchool, weekStart, weekdayShort } from '@/utils/dates'
import { nowMs } from '@/utils/clock'
import { useRefsStore } from '@/stores/refs'
import type { Locale } from '@/i18n'

/** Trial booking: teacher → that teacher's groups → the group's calendar → a lesson day → save. */
const props = defineProps<{ branchId: number | null; busy?: boolean }>()
const emit = defineEmits<{ pick: [Lesson] }>()
const { t, locale } = useI18n()
const loc = computed(() => locale.value as Locale)
const WEEKS = 5

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
  const start = weekStart(schoolNow())
  const list = await academicsApi.lessons({ from: isoDate(start), to: isoDate(addDays(start, WEEKS * 7 - 1)), group_id: g.id }).catch(() => [])
  if (group.value?.id !== g.id) return
  const now = nowMs()
  lessons.value = list.filter((l) => l.status === 'planned' && new Date(l.starts_at).getTime() > now).sort((a, b) => a.starts_at.localeCompare(b.starts_at))
}

/** Five weeks from this Monday; each day carries the group's lessons that can still be booked. */
const weeks = computed(() => {
  const start = weekStart(schoolNow())
  const today = schoolNow()
  return Array.from({ length: WEEKS }, (_, w) => Array.from({ length: 7 }, (_, d) => {
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
    <UiSkeleton v-if="!groups" :lines="3" />
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
.tp-day.past { opacity: .45 }
.tp-day.today > span { color: var(--red-ink); font-weight: 700 }
.tp-slot { border: 0; border-radius: 6px; padding: 4px 0; font: inherit; font-size: 12px; font-weight: 600; cursor: pointer; background: var(--navy-100); color: var(--accent-ink) }
.tp-slot.sel { background: var(--red); color: #fff }
.tp-foot { display: flex; gap: 10px; align-items: center; border-top: 1px solid var(--line); padding-top: 10px; font-size: 13px }
</style>
