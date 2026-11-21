<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiCard, UiSelect, UiSkeleton } from '@/components/ui'
import { studentsApi, type AttendanceMark } from '@/api/students'
import { schoolNow } from '@/utils/dates'
import { intlLocale, type Locale } from '@/i18n'

/** Attendance of one month as a calendar: day numbers, every lesson coloured by its mark, frozen days shaded. */
const props = defineProps<{ studentId: number }>()
const { t, locale } = useI18n()
const loc = computed(() => locale.value as Locale)
type Mark = AttendanceMark & { date: string; time: string }
const CLS = { present: 'p', late: 'l', absent: 'a', excused: 'f' } as const
const KEY = { present: 'p', late: 'l', absent: 'a', excused: 'e' } as const

const now = schoolNow()
const year = ref(now.getFullYear())
const month = ref(now.getMonth() + 1)
const marks = ref<Mark[] | null>(null)
const frozen = ref<Set<string>>(new Set())
const key = computed(() => `${year.value}-${String(month.value).padStart(2, '0')}`)
let seq = 0
watch(() => [props.studentId, key.value], async () => {
  const my = ++seq
  marks.value = null
  const r = await studentsApi.attendanceMonth(props.studentId, key.value).catch(() => ({ marks: [], frozen: [] as string[] }))
  if (my !== seq) return
  marks.value = r.marks
  frozen.value = new Set(r.frozen)
}, { immediate: true })

const monthOptions = computed(() => Array.from({ length: 12 }, (_, i) => {
  const s = new Date(2026, i, 1).toLocaleDateString(intlLocale(loc.value), { month: 'long' })
  return { value: i + 1, label: s.charAt(0).toUpperCase() + s.slice(1) }
}))
const yearOptions = computed(() => Array.from({ length: now.getFullYear() - 2017 }, (_, i) => ({ value: now.getFullYear() - i, label: String(now.getFullYear() - i) })))
const weekdays = computed(() => Array.from({ length: 7 }, (_, i) => new Date(2026, 5, 1 + i).toLocaleDateString(intlLocale(loc.value), { weekday: 'short' })))
/** Weeks start on Monday; empty cells pad the first week. */
const cells = computed(() => {
  const first = new Date(year.value, month.value - 1, 1)
  const pad = (first.getDay() + 6) % 7
  const n = new Date(year.value, month.value, 0).getDate()
  const out: ({ n: number; iso: string; marks: Mark[]; frozen: boolean } | null)[] = Array.from({ length: pad }, () => null)
  for (let d = 1; d <= n; d++) {
    const iso = `${key.value}-${String(d).padStart(2, '0')}`
    out.push({ n: d, iso, marks: (marks.value ?? []).filter((m) => m.date === iso), frozen: frozen.value.has(iso) })
  }
  return out
})
const count = (s: AttendanceMark['status']) => (marks.value ?? []).filter((m) => m.status === s).length
const rate = computed(() => {
  const counted = (marks.value ?? []).filter((m) => m.status !== 'excused')
  return counted.length ? Math.round((counted.filter((m) => m.status === 'present' || m.status === 'late').length / counted.length) * 100) : null
})
const tip = (m: Mark) => `${m.time}${m.group ? ` · ${m.group}` : ''} · ${t(`students.att.${KEY[m.status]}`)}${m.grade ? ` · ${m.grade}` : ''}${m.comment ? ` · ${m.comment}` : ''}`
</script>

<template>
  <UiCard :title="t('students.att.title')">
    <template v-if="rate !== null" #actions><b class="num">{{ rate }}%</b></template>
    <div class="ac-top">
      <UiSelect v-model="month" :options="monthOptions" :label="t('nv.cal.month')" />
      <UiSelect v-model="year" :options="yearOptions" :label="t('nv.cal.year')" />
    </div>
    <UiSkeleton v-if="!marks" :lines="4" />
    <template v-else>
      <div class="ac-grid" role="grid" :aria-label="t('students.att.title')">
        <span v-for="w in weekdays" :key="w" class="wd">{{ w }}</span>
        <template v-for="(c, i) in cells" :key="i">
          <span v-if="!c" />
          <div v-else class="day" :class="[c.marks.length === 1 ? CLS[c.marks[0]!.status] : undefined, { frozen: c.frozen && !c.marks.length, many: c.marks.length > 1 }]"
            :title="c.marks.length ? c.marks.map(tip).join('\n') : c.frozen ? t('nv.cal.frozen') : undefined">
            <b class="num">{{ c.n }}</b>
            <span v-if="c.marks.length > 1" class="dots"><i v-for="m in c.marks" :key="m.lesson_id" :class="CLS[m.status]" /></span>
          </div>
        </template>
      </div>
      <div class="mini-leg">
        <span><i style="background: var(--ok)" />{{ t('students.att.p') }} · {{ count('present') }}</span>
        <span><i style="background: var(--warn)" />{{ t('students.att.l') }} · {{ count('late') }}</span>
        <span><i style="background: var(--red)" />{{ t('students.att.a') }} · {{ count('absent') }}</span>
        <span><i style="background: var(--grid)" />{{ t('students.att.e') }} · {{ count('excused') }}</span>
        <span v-if="frozen.size"><i class="fz" />{{ t('nv.cal.frozen') }} · {{ frozen.size }}</span>
      </div>
    </template>
  </UiCard>
</template>

<style scoped>
.ac-top { display: flex; gap: 8px; margin-bottom: 12px }
.ac-grid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 5px; margin-bottom: 12px }
.wd { text-align: center; font-size: 11px; color: var(--muted); text-transform: lowercase; padding-bottom: 2px }
.day { aspect-ratio: 1; max-height: 46px; border-radius: 8px; border: 1px solid var(--line); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px; font-size: 13px; color: var(--muted); width: 100% }
.day b { font-weight: 500 }
.day.p, .day.l, .day.a { color: #fff; border-color: transparent }
.day.p b, .day.l b, .day.a b, .day.f b { font-weight: 700 }
.day.p { background: var(--ok) }
.day.l { background: var(--warn) }
.day.a { background: var(--red) }
.day.f { background: var(--grid); color: var(--ink); border-color: transparent }
.day.many { border-color: var(--navy); color: var(--ink) }
.day.frozen { background: repeating-linear-gradient(45deg, var(--navy-50), var(--navy-50) 4px, var(--surface) 4px, var(--surface) 8px) }
.dots { display: inline-flex; gap: 2px }
.dots i { width: 7px; height: 7px; border-radius: 2px }
.dots i.p { background: var(--ok) }
.dots i.l { background: var(--warn) }
.dots i.a { background: var(--red) }
.dots i.f { background: var(--grid) }
.fz { background: repeating-linear-gradient(45deg, var(--navy-50), var(--navy-50) 2px, var(--line) 2px, var(--line) 4px) !important }
</style>
