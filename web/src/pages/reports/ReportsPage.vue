<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiCard, UiEmptyState, UiInput, UiSelect, UiSkeleton, UiTabs } from '@/components/ui'
import { ApiError } from '@/api/http'
import { reportsApi, type ManagerRow, type Report, type TeacherRow } from '@/api/reports'
import { useBranchStore } from '@/stores/branch'
import { useToastStore } from '@/stores/toast'
import type { Locale } from '@/i18n'
import { isoDate, money, schoolNow } from '@/utils/dates'
import { keptRef } from '@/utils/kept'

const { t, locale } = useI18n()
const loc = computed(() => locale.value as Locale)
const branch = useBranchStore()
const toast = useToastStore()
const now = schoolNow()
const tab = keptRef<'managers' | 'teachers'>('reports.tab', () => 'managers')
const f = reactive({ from: isoDate(new Date(now.getFullYear(), now.getMonth(), 1)), to: isoDate(now) })
const who = ref(0)
const mg = ref<Report<ManagerRow> | null>(null)
const tc = ref<Report<TeacherRow> | null>(null)
const loading = ref(true)
const exporting = ref(false)
let seq = 0

const filter = () => ({ date_from: f.from, date_to: f.to, branch_id: branch.filterId, [tab.value === 'managers' ? 'manager_id' : 'teacher_id']: who.value || null })
async function load() {
  const my = ++seq
  loading.value = true
  try {
    if (tab.value === 'managers') {
      const d = await reportsApi.managers(filter())
      if (my === seq) mg.value = d
    } else {
      const d = await reportsApi.teachers(filter())
      if (my === seq) tc.value = d
    }
  } catch {
    if (my === seq) (tab.value === 'managers' ? mg : tc).value = null
  } finally {
    if (my === seq) loading.value = false
  }
}
watch(tab, () => {
  who.value = 0
  load()
})
watch(() => [f.from, f.to, branch.filterId, who.value], load)
onMounted(load)

async function exportXlsx() {
  exporting.value = true
  try {
    await (tab.value === 'managers' ? reportsApi.managersXlsx(filter()) : reportsApi.teachersXlsx(filter()))
  } catch (e) {
    toast.error(e instanceof ApiError ? e.detail || t('errors.generic') : t('errors.generic'))
  } finally {
    exporting.value = false
  }
}

const tabs = computed(() => [
  { value: 'managers' as const, label: t('nv.rep.managers') },
  { value: 'teachers' as const, label: t('nv.rep.teachers') },
])
const data = computed(() => (tab.value === 'managers' ? mg.value : tc.value))
const people = computed(() => [
  { value: 0, label: t(tab.value === 'managers' ? 'nv.rep.allManagers' : 'nv.rep.allTeachers') },
  ...(data.value?.people ?? []).map((p) => ({ value: p.id, label: p.name })),
])
const MG = ['new', 'worked', 'actions', 'trial_booked', 'trial_done', 'paid', 'lost', 'conversion', 'tasks_done', 'tasks_overdue', 'sales', 'sales_sum', 'bonus'] as const
const TC = ['planned', 'held', 'held_pct', 'not_marked', 'cancelled', 'subs', 'plan_pct', 'attendance_pct', 'pay_lessons', 'pay_other', 'pay_total'] as const
const cols = computed<readonly string[]>(() => (tab.value === 'managers' ? MG : TC))
const MONEY = new Set(['sales_sum', 'bonus', 'pay_lessons', 'pay_other', 'pay_total'])
const PCT = new Set(['conversion', 'held_pct', 'plan_pct', 'attendance_pct'])
function cell(row: Record<string, unknown> | undefined, k: string) {
  const v = row?.[k] as number | null | undefined
  if (v === null || v === undefined) return '—'
  return MONEY.has(k) ? money(v, loc.value) : PCT.has(k) ? `${v}%` : String(v)
}
const rows = computed(() => (data.value?.rows ?? []) as unknown as (Record<string, unknown> & { user_id: number; name: string })[])
const total = computed(() => data.value?.total as Record<string, unknown> | undefined)
const kpis = computed(() => (tab.value === 'managers' ? ['new', 'worked', 'paid', 'conversion', 'sales_sum'] : ['planned', 'held', 'held_pct', 'not_marked', 'pay_total']))
</script>

<template>
  <div class="ph">
    <div><h1>{{ t('nav.reports') }}</h1></div>
    <span class="sp" />
    <UiButton icon="dl" :loading="exporting" data-testid="reports-export" @click="exportXlsx">{{ t('nv.exportXlsx') }}</UiButton>
  </div>
  <UiTabs v-model="tab" :items="tabs" :label="t('nav.reports')" />
  <div class="toolbar">
    <UiInput v-model="f.from" type="date" :max="f.to" class="tb-date" :aria-label="t('payments.from')" />
    <span class="muted">—</span>
    <UiInput v-model="f.to" type="date" :min="f.from" class="tb-date" :aria-label="t('payments.to')" />
    <UiSelect v-model="who" :options="people" :label="t(tab === 'managers' ? 'nv.rep.manager' : 'nv.rep.teacher')" data-testid="reports-who" />
  </div>
  <div v-if="loading && !data" class="card" style="padding: 18px"><UiSkeleton :lines="6" /></div>
  <UiEmptyState v-else-if="!data || !rows.length" icon="kpi" :title="t('nv.rep.empty')" />
  <template v-else>
    <div class="grid kpis" style="margin-bottom: 16px">
      <div v-for="k in kpis" :key="k" class="card kpi"><div class="k">{{ t(`nv.rep.c.${k}`) }}</div><div class="v num">{{ cell(total, k) }}</div></div>
    </div>
    <UiCard flush>
      <div class="scroll-x">
        <table class="rep" :class="{ dim: loading }">
          <thead>
            <tr><th>{{ t(tab === 'managers' ? 'nv.rep.manager' : 'nv.rep.teacher') }}</th><th v-for="k in cols" :key="k" class="r">{{ t(`nv.rep.c.${k}`) }}</th></tr>
          </thead>
          <tbody class="num">
            <tr v-for="r in rows" :key="r.user_id" :class="{ on: who === r.user_id }">
              <td><button type="button" class="linkbtn" @click="who = who === r.user_id ? 0 : r.user_id">{{ r.name }}</button></td>
              <td v-for="k in cols" :key="k" class="r" :class="{ bad: (k === 'tasks_overdue' || k === 'not_marked') && Number(r[k]) > 0 }">{{ cell(r, k) }}</td>
            </tr>
          </tbody>
          <tfoot v-if="rows.length > 1" class="num">
            <tr><td><b>{{ t('nv.rep.total') }}</b></td><td v-for="k in cols" :key="k" class="r"><b>{{ cell(total, k) }}</b></td></tr>
          </tfoot>
        </table>
      </div>
    </UiCard>
  </template>
</template>

<style scoped>
.rep { min-width: 1280px }
.rep td { white-space: nowrap }
.rep th { white-space: normal; vertical-align: bottom; font-size: 12px; line-height: 1.25; max-width: 110px }
.rep th:first-child, .rep td:first-child { position: sticky; left: 0; background: var(--surface); z-index: 1; white-space: nowrap }
.rep tr.on td { background: var(--navy-50) }
.rep td.bad { color: var(--red); font-weight: 600 }
.rep tfoot td { border-top: 2px solid var(--line) }
.rep.dim { opacity: 0.6 }
</style>
