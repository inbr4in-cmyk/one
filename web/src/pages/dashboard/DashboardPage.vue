<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiCard, UiChip, UiEmptyState, UiIcon, UiPeriod, UiSkeleton } from '@/components/ui'
import BarChart from '@/components/charts/BarChart.vue'
import HBars from '@/components/charts/HBars.vue'
import { financeApi, type Dashboard, type Ratings } from '@/api/finance'
import { academicsApi, type Lesson } from '@/api/academics'
import { crmApi, type Lead } from '@/api/crm'
import { useAuthStore } from '@/stores/auth'
import { useBranchStore } from '@/stores/branch'
import { useRefsStore } from '@/stores/refs'
import { useSourceLabel } from '@/composables/useSourceLabel'
import { hm, isoDate, money, waitLabel, schoolNow } from '@/utils/dates'
import { compactMoney, num, periodLabel, periodOf } from '@/utils/period'
import { tone } from '@/utils/levels'
import type { Locale } from '@/i18n'

const { t, locale } = useI18n()
const auth = useAuthStore()
const branch = useBranchStore()
const refs = useRefsStore()
const srcLabel = useSourceLabel()
const loc = computed(() => locale.value as Locale)

const data = ref<Dashboard | null>(null)
const ratings = ref<Ratings | null>(null)
const lessons = ref<Lesson[] | null>(null)
const stale = ref<Lead[] | null>(null)
const failed = ref(false)
const exporting = ref(false)
/** Month the KPIs and ratings describe; today's lessons and waiting leads are always live */
const period = ref(periodOf())
const isCurrent = computed(() => period.value === periodOf())

const SRC: Record<string, { cls: string; icon: string }> = {
  instagram: { cls: 'ig', icon: 'ig' }, whatsapp: { cls: 'wa', icon: 'wa' }, qr: { cls: 'qr', icon: 'qr' }, site: { cls: 'web', icon: 'globe' },
  referral: { cls: 'ref', icon: 'ref' }, sales: { cls: 'call', icon: 'phone' }, return: { cls: 'call', icon: 'lead-return' }, walk_in: { cls: 'call', icon: 'user' },
}

async function load() {
  failed.value = false
  const b = { branch_id: branch.filterId, period: period.value }
  const today = isoDate(schoolNow())
  const [d, r] = await Promise.allSettled([financeApi.dashboard(b), financeApi.ratings(b)])
  if (d.status === 'fulfilled') data.value = d.value
  else failed.value = true
  ratings.value = r.status === 'fulfilled' ? r.value : null
  if (auth.can('schedule.view')) {
    lessons.value = await academicsApi.lessons({ from: today, to: today, branch_id: branch.filterId }).catch(() => [])
  }
  if (auth.can('crm.view')) {
    const board = await crmApi.board({ pipeline: 'main', branch_id: branch.filterId }).catch(() => null)
    stale.value = (board?.columns.flatMap((c) => c.leads) ?? [])
      .filter((l) => l.waiting_min !== null && l.waiting_min > 30)
      .sort((a, b) => (b.waiting_min ?? 0) - (a.waiting_min ?? 0))
  }
}
onMounted(load)
watch([() => branch.filterId, period], load)

const hello = computed(() => {
  const h = schoolNow().getHours()
  const first = auth.user?.full_name.split(' ')[0] ?? ''
  return t(h < 12 ? 'dash.morning' : h < 18 ? 'dash.day' : 'dash.evening', { name: first })
})
const todayLabel = computed(() => {
  const s = schoolNow().toLocaleDateString(locale.value === 'kk' ? 'kk-KZ' : 'ru-RU', { weekday: 'long', day: 'numeric', month: 'long' })
  return s.charAt(0).toUpperCase() + s.slice(1)
})
const scope = computed(() => (branch.filterId === null ? t('branch.all') : branch.current.name))
const units = computed(() => ({ m: t('time.min'), h: t('time.h'), d: t('time.d') }))

const cm = (n: number) => compactMoney(n, loc.value)
const unitLabel = (u: 'mln' | 'k' | '') => (u ? t(`dash.unit.${u}`) : '')
const trend = computed(() => {
  const tr = data.value?.revenue_trend
  if (!tr) return null
  const cur = periodOf()
  return tr.map((x) => ({
    key: x.period,
    label: periodLabel(x.period, loc.value, { month: 'short' }).replace('.', ''),
    value: x.revenue,
    soft: x.period === cur,
    note: x.period === cur ? t('dash.inProgress') : undefined,
  }))
})
const axisTick = (v: number) => {
  const c = cm(v)
  return c.unit ? `${c.v} ${unitLabel(c.unit)}` : c.v
}
const sources = computed(() => Object.entries(data.value?.leads_by_source ?? {})
  .map(([k, v]) => ({ key: k, label: srcLabel(k), value: v, icon: SRC[k]?.icon ?? 'user', iconCls: SRC[k]?.cls ?? 'call' }))
  .sort((a, b) => b.value - a.value))
const upcoming = computed(() => {
  const now = Date.now()
  return (lessons.value ?? []).filter((l) => l.status !== 'cancelled' && new Date(l.ends_at).getTime() > now).slice(0, 5)
})
const teacherRows = computed(() => (ratings.value?.teachers ?? []).slice(0, 6))
const salesRows = computed(() => (ratings.value?.sales ?? []).slice(0, 6))

async function exportExcel() {
  exporting.value = true
  try {
    await financeApi.exportPayments({ period: period.value, branch_id: branch.filterId })
  } catch {
    /* toast */
  } finally {
    exporting.value = false
  }
}
</script>

<template>
  <div class="ph">
    <div><h1>{{ hello }}</h1><p>{{ todayLabel }} · {{ t('dash.summary', { scope }) }}</p></div>
    <span class="sp" />
    <UiPeriod v-model="period" />
    <UiButton v-if="auth.can('finance.export')" icon="file" :loading="exporting" @click="exportExcel">{{ t('dash.excel') }}</UiButton>
  </div>

  <UiEmptyState v-if="failed && !data" icon="dash" :title="t('errors.generic')"><UiButton icon="history" @click="load">{{ t('common.retry') }}</UiButton></UiEmptyState>

  <template v-else>
    <div class="kpis stagger">
      <template v-if="!data"><div v-for="i in 6" :key="i" class="card kpi"><UiSkeleton :lines="3" /></div></template>
      <template v-else>
        <div class="card kpi">
          <div class="k"><UiIcon name="users" :size="18" />{{ t('dash.k.students') }}</div>
          <div class="v num">{{ num(data.students_active, loc) }}</div>
          <span class="muted" style="font-size: 12px">{{ t('dash.k.lowBalance', { n: data.low_balance }) }}</span>
        </div>
        <div v-if="data.leads_month !== undefined" class="card kpi">
          <div class="k"><UiIcon name="crm" :size="18" />{{ t('dash.k.leads') }}</div>
          <div class="v num">{{ num(data.leads_month, loc) }}</div>
          <span class="muted" style="font-size: 12px">{{ data.conversion === null || data.conversion === undefined ? t('dash.k.noConversion') : t('dash.k.conversion', { n: num(data.conversion, loc, 1) }) }}</span>
        </div>
        <div v-if="data.revenue_month !== undefined" class="card kpi">
          <div class="k"><UiIcon name="wallet" :size="18" />{{ t('dash.k.revenue', { month: periodLabel(data.period, loc, { month: 'long' }) }) }}</div>
          <div class="v num">{{ cm(data.revenue_month).v }}<small> {{ unitLabel(cm(data.revenue_month).unit) }} ₸</small></div>
          <span class="muted" style="font-size: 12px"><template v-if="isCurrent">{{ t('dash.k.today', { sum: money(data.revenue_today, loc) }) }} · </template>{{ t('dash.k.sales', { n: data.sales_month ?? 0 }) }}</span>
        </div>
        <div class="card kpi">
          <div class="k"><UiIcon name="check" :size="18" />{{ t('dash.k.attendance') }}</div>
          <div class="v num">{{ data.attendance_rate === null ? '—' : num(data.attendance_rate, loc, 1) }}<small v-if="data.attendance_rate !== null">%</small></div>
          <span v-if="isCurrent" class="muted" style="font-size: 12px">{{ t('dash.k.lessonsToday', { n: data.lessons_today }) }}</span>
          <div v-if="data.attendance_rate !== null" class="bar-track"><i :style="{ width: `${data.attendance_rate}%` }" /></div>
        </div>
        <div class="card kpi">
          <div class="k"><UiIcon name="refusal" :size="18" />{{ t('dash.k.leftPaused') }}</div>
          <div class="kpi-split">
            <RouterLink :to="{ path: '/students', query: { status: 'left' } }" class="kpi-link"><b class="v num">{{ num(data.students_left ?? 0, loc) }}</b><span>{{ t('dash.k.left') }}</span></RouterLink>
            <RouterLink :to="{ path: '/students', query: { status: 'frozen' } }" class="kpi-link"><b class="v num">{{ num(data.students_frozen ?? 0, loc) }}</b><span>{{ t('dash.k.paused') }}</span></RouterLink>
          </div>
          <span class="muted" style="font-size: 12px">{{ t('dash.k.leftMonth', { n: data.left_month ?? 0 }) }}</span>
        </div>
        <div class="card kpi">
          <div class="k"><UiIcon name="alert" :size="18" :style="data.debtors ? { color: 'var(--red)' } : undefined" />{{ t('dash.k.debtors') }}</div>
          <div class="v num">{{ num(data.debtors, loc) }}</div>
          <span class="delta" :class="data.debtors ? 'down' : 'muted'">{{ data.debtors ? t('dash.k.debtorsNote') : t('dash.k.noDebtors') }}</span>
        </div>
      </template>
    </div>

    <div v-if="trend || sources.length" class="grid dash-a">
      <UiCard v-if="trend" :title="t('dash.revenueTitle')">
        <template #actions><span class="chip">{{ scope }}</span></template>
        <BarChart :items="trend" :format="(v) => money(v, loc)" :tick="axisTick" :caption="t('dash.revenueTitle')" />
        <div class="mini-leg" style="margin-top: 6px">
          <span><i style="background: var(--chart-bar)" />{{ t('dash.fact') }}</span>
          <span><i style="background: var(--chart-bar-soft)" />{{ t('dash.currentMonth') }}</span>
        </div>
      </UiCard>
      <UiCard v-if="data?.leads_by_source" :title="t('dash.sourcesTitle')">
        <template #actions><span class="muted" style="font-size: 12px">{{ t('dash.sourcesNote', { n: data.leads_month ?? 0 }) }}</span></template>
        <HBars v-if="sources.length" :items="sources" />
        <p v-else class="muted m0">{{ t('dash.noLeads') }}</p>
      </UiCard>
    </div>

    <div class="grid dash-b">
      <UiCard v-if="auth.can('schedule.view')" :title="t('dash.upcoming')">
        <template #actions><UiButton size="sm" variant="ghost" icon-end="arrow" to="/schedule">{{ t('nav.schedule') }}</UiButton></template>
        <UiSkeleton v-if="!lessons" :lines="4" />
        <template v-else-if="upcoming.length">
          <RouterLink v-for="l in upcoming" :key="l.id" :to="auth.can('attendance.view') ? `/attendance/${l.id}` : '/schedule'" class="list-row">
            <span class="t num">{{ hm(l.starts_at, loc) }}</span>
            <div class="grow"><b>{{ l.group_name ?? (l.kind === 'support' ? 'Support · ' + (l.topic ?? '') : t('schedule.individual')) }}<template v-if="refs.level(l.level_id)"> · {{ refs.level(l.level_id)?.name }}</template></b><span>{{ l.teacher_name }} · {{ l.room_name }}<template v-if="l.trials"> · {{ t('schedule.trials', { n: l.trials }) }}</template></span></div>
            <span v-if="refs.level(l.level_id)" class="lv" :style="{ '--c': tone(refs.level(l.level_id)?.color) }">{{ refs.level(l.level_id)?.code }}</span>
          </RouterLink>
        </template>
        <p v-else class="muted m0">{{ t('dash.noLessons') }}</p>
      </UiCard>

      <UiCard v-if="auth.can('crm.view')" :title="t('dash.stale')">
        <template #actions>
          <UiChip v-if="stale?.length" tone="red" small>{{ stale.length }}</UiChip>
          <UiButton size="sm" variant="ghost" icon-end="arrow" to="/crm">{{ t('dash.toCrm') }}</UiButton>
        </template>
        <UiSkeleton v-if="!stale" :lines="4" />
        <template v-else-if="stale.length">
          <RouterLink v-for="l in stale.slice(0, 5)" :key="l.id" :to="{ path: '/crm', query: { lead: l.id } }" class="list-row">
            <span class="srcico" :class="SRC[l.source]?.cls ?? 'call'"><svg><use :href="`#i-${SRC[l.source]?.icon ?? 'user'}`" /></svg></span>
            <div class="grow"><b>{{ l.full_name }}</b><span>{{ l.owner_name ?? t('crm.unassigned') }}</span></div>
            <span class="late"><UiIcon name="clock" :size="16" />{{ waitLabel(l.waiting_min ?? 0, units) }}</span>
          </RouterLink>
        </template>
        <p v-else class="muted m0">{{ t('dash.noStale') }}</p>
      </UiCard>

      <UiCard v-if="ratings" :title="t('dash.teachers')" flush>
        <template #actions><span class="muted" style="font-size: 12px">{{ periodLabel(ratings.period, loc) }}</span></template>
        <div v-if="teacherRows.length" class="scroll-x">
          <table class="tbl">
            <thead><tr><th>{{ t('dash.r.teacher') }}</th><th class="r">{{ t('dash.r.lessons') }}</th><th class="r">{{ t('dash.r.avg') }}</th><th class="r">{{ t('dash.r.attendance') }}</th></tr></thead>
            <tbody class="num">
              <tr v-for="(r, i) in teacherRows" :key="r.user_id"><td><span class="rank-n" :class="{ g: i < 3 }">{{ i + 1 }}</span>{{ r.full_name }}</td><td class="r">{{ r.lessons }}</td><td class="r">{{ num(r.avg_students, loc, 1) }}</td><td class="r">{{ r.attendance_rate === null ? '—' : `${num(r.attendance_rate, loc, 1)}%` }}</td></tr>
            </tbody>
          </table>
        </div>
        <p v-else class="muted m0 card-pad">{{ t('dash.noRatings') }}</p>
      </UiCard>

      <UiCard v-if="ratings" :title="t('dash.sales')" flush>
        <div v-if="salesRows.length" class="scroll-x">
          <table class="tbl">
            <thead><tr><th>{{ t('dash.r.manager') }}</th><th class="r">{{ t('dash.r.trials') }}</th><th class="r">{{ t('dash.r.salesN') }}</th><th class="r">{{ t('dash.r.returns') }}</th></tr></thead>
            <tbody class="num">
              <tr v-for="(r, i) in salesRows" :key="r.user_id"><td><span class="rank-n" :class="{ g: i < 3 }">{{ i + 1 }}</span>{{ r.full_name }}</td><td class="r">{{ r.trial_visit ?? 0 }}</td><td class="r">{{ r.sale ?? 0 }}</td><td class="r">{{ r.return ?? 0 }}</td></tr>
            </tbody>
          </table>
        </div>
        <p v-else class="muted m0 card-pad">{{ t('dash.noSales') }}</p>
      </UiCard>
    </div>
  </template>
</template>

<style scoped>
.kpi-split { display: flex; gap: 18px }
.kpi-link { display: grid; color: inherit; text-decoration: none; border-radius: 8px }
.kpi-link span { font-size: 12px; color: var(--muted) }
.kpi-link:hover b { color: var(--red-ink); text-decoration: underline }
</style>
