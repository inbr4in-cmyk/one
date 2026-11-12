<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiCard, UiEmptyState, UiSegmented, UiSkeleton } from '@/components/ui'
import { payrollApi, type DayStatus, type Timesheet, type TimesheetPerson } from '@/api/payroll'
import { useToastStore } from '@/stores/toast'
import { isoDate, money } from '@/utils/dates'
import { apiErr } from '@/utils/err'
import type { Locale } from '@/i18n'

/** Табель: the branch admin marks each staff member's days; salaried staff are paid by the days worked. */
const props = defineProps<{ period: string; branchId: number | null }>()
const { t, locale } = useI18n()
const loc = computed(() => locale.value as Locale)
const toast = useToastStore()
const ts = ref<Timesheet | null>(null)
const brush = ref<DayStatus | 'clear'>('work')
const saving = ref<string | null>(null)
const STATUSES: DayStatus[] = ['work', 'off', 'sick', 'vacation', 'absent']
const brushOptions = computed(() => [...STATUSES.map((s) => ({ value: s, label: t(`payroll.ts.s.${s}`) })), { value: 'clear' as const, label: t('payroll.ts.clear') }])
const todayIso = isoDate(new Date())

const days = computed(() => {
  const [y = 2026, m = 1] = props.period.split('-').map(Number)
  const out: { iso: string; d: number; wd: number }[] = []
  for (let d = new Date(y, m - 1, 1); d.getMonth() === m - 1; d.setDate(d.getDate() + 1)) {
    out.push({ iso: isoDate(d), d: d.getDate(), wd: (d.getDay() + 6) % 7 })
  }
  return out
})
const editable = computed(() => !!ts.value?.can_edit && !ts.value.locked)
const isWorkday = (wd: number) => ts.value?.workdays.includes(wd) ?? wd < 6

async function load() {
  ts.value = null
  if (props.branchId === null) return
  try { ts.value = await payrollApi.timesheet(props.period, props.branchId) } catch (e) { toast.error(apiErr(e) ?? t('errors.generic')) }
}
watch(() => [props.period, props.branchId], load, { immediate: true })

async function apply(p: TimesheetPerson, isos: string[]) {
  if (!editable.value || props.branchId === null || !isos.length) return
  const status = brush.value === 'clear' ? null : brush.value
  if (status === 'work') isos = isos.filter((x) => x <= todayIso)
  if (!isos.length) return
  saving.value = `${p.user_id}`
  try {
    await payrollApi.setDays({ user_id: p.user_id, branch_id: props.branchId, days: isos, status })
    const fresh = await payrollApi.timesheet(props.period, props.branchId)
    ts.value = fresh
  } catch (e) {
    toast.error(apiErr(e) ?? t('errors.generic'))
  } finally {
    saving.value = null
  }
}
function fill(p: TimesheetPerson) {
  const prev = brush.value
  brush.value = 'work'
  apply(p, days.value.filter((x) => isWorkday(x.wd) && x.iso <= todayIso && !p.days[x.iso]).map((x) => x.iso)).finally(() => (brush.value = prev))
}
const wdShort = (wd: number) => new Intl.DateTimeFormat(loc.value === 'kk' ? 'kk-KZ' : 'ru-RU', { weekday: 'narrow' }).format(new Date(2024, 0, 1 + wd))
</script>

<template>
  <div v-if="branchId === null" class="alert info"><span>{{ t('payroll.ts.pickBranch') }}</span></div>
  <template v-else>
    <div v-if="ts?.locked || (ts && !ts.can_edit)" class="alert info">
      <span>{{ ts?.locked ? t('payroll.ts.locked') : t('payroll.ts.readonly') }}</span>
    </div>
    <div v-if="editable" class="toolbar ts-tools">
      <span class="muted">{{ t('payroll.ts.brush') }}:</span>
      <UiSegmented v-model="brush" :options="brushOptions" :label="t('payroll.ts.brush')" size="sm" />
    </div>
    <UiCard flush>
      <div v-if="!ts" class="card-pad"><UiSkeleton :lines="6" /></div>
      <UiEmptyState v-else-if="!ts.people.length" icon="users" :title="t('payroll.ts.empty')" />
      <div v-else class="ts-wrap">
        <table class="ts">
          <thead>
            <tr>
              <th class="ts-name" />
              <th v-for="x in days" :key="x.iso" :class="{ we: !isWorkday(x.wd), today: x.iso === todayIso }"><span>{{ wdShort(x.wd) }}</span><b>{{ x.d }}</b></th>
              <th class="ts-sum">{{ t('payroll.ts.worked') }}</th>
              <th class="ts-sum">{{ t('payroll.ts.amount') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in ts.people" :key="p.user_id" :class="{ busy: saving === `${p.user_id}` }">
              <th class="ts-name"><div>
                <b>{{ p.full_name }}</b>
                <span class="muted">{{ p.position ?? '' }}</span>
                <UiButton v-if="editable" size="sm" variant="ghost" class="ts-fill" :title="t('payroll.ts.fill')" @click="fill(p)">{{ t('payroll.ts.fillShort') }}</UiButton>
              </div></th>
              <td v-for="x in days" :key="x.iso" :class="[p.days[x.iso], { we: !isWorkday(x.wd) }]">
                <button v-if="editable" type="button" :aria-label="`${p.full_name}, ${x.iso}: ${p.days[x.iso] ? t(`payroll.ts.s.${p.days[x.iso]}`) : '—'}`" @click="apply(p, [x.iso])">{{ p.days[x.iso] ? t(`payroll.ts.short.${p.days[x.iso]}`) : '' }}</button>
                <span v-else>{{ p.days[x.iso] ? t(`payroll.ts.short.${p.days[x.iso]}`) : '' }}</span>
              </td>
              <td class="ts-sum num"><b>{{ p.worked }}</b> <span class="muted">{{ t('payroll.ts.ofNorm', { n: ts.norm }) }}</span></td>
              <td class="ts-sum num">{{ p.amount !== null ? money(p.amount, loc) : t('payroll.ts.noSalary') }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </UiCard>
  </template>
</template>

<style scoped>
.ts-tools { gap: 8px; flex-wrap: wrap; align-items: center }
.ts-wrap { overflow-x: auto }
.ts { border-collapse: collapse; font-size: 12px; min-width: 100% }
.ts th, .ts td { border-bottom: 1px solid var(--line); text-align: center; padding: 0 }
.ts thead th { padding: 6px 2px; font-weight: 500; color: var(--muted) }
.ts thead th span { display: block; font-size: 10px }
.ts thead th b { color: var(--ink) }
.ts thead th.today b { color: var(--red-600) }
.ts .we { background: var(--navy-50) }
.ts-name { position: sticky; left: 0; z-index: 1; background: var(--surface); text-align: left !important; padding: 6px 10px !important; min-width: 180px }
.ts-name > div { display: grid; gap: 2px }
.ts-name .muted { font-size: 11px }
.ts-fill { justify-self: start; margin-top: 2px }
.ts td { width: 28px; height: 34px }
.ts td button { width: 100%; height: 100%; min-height: 34px; border: 0; background: none; cursor: pointer; font: inherit; font-weight: 600 }
.ts td button:hover { outline: 2px solid var(--navy); outline-offset: -2px }
.ts td.work { background: var(--ok-bg); color: var(--ok) }
.ts td.sick, .ts td.vacation { background: var(--info-bg); color: var(--info) }
.ts td.absent { background: var(--red-100); color: var(--red-600) }
.ts td.off { color: var(--muted) }
.ts-sum { white-space: nowrap; padding: 0 10px !important; text-align: right !important }
tr.busy { opacity: 0.55 }
</style>
