<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { UiButton, UiCard, UiChip, UiEmptyState, UiIcon, UiInput, UiModal, UiSegmented, UiSelect, UiSkeleton } from '@/components/ui'
import HBars from '@/components/charts/HBars.vue'
import { financeApi, type Dashboard, type DayReport, type Ratings } from '@/api/finance'
import { crmApi, type Analytics } from '@/api/crm'
import { useAuthStore } from '@/stores/auth'
import { useBranchStore } from '@/stores/branch'
import { useRefsStore } from '@/stores/refs'
import { useSourceLabel } from '@/composables/useSourceLabel'
import { money, todayIso, schoolNow } from '@/utils/dates'
import { num, periodLabel } from '@/utils/period'
import { formatPhone } from '@/utils/phone'
import type { Locale } from '@/i18n'

const { t, locale } = useI18n()
const auth = useAuthStore()
const router = useRouter()
const branch = useBranchStore()
const refs = useRefsStore()
const srcLabel = useSourceLabel()
const loc = computed(() => locale.value as Locale)

const data = ref<Dashboard | null>(null)
const ratings = ref<Ratings | null>(null)
const funnel = ref<Analytics | null>(null)
/** The report is for one day or for a whole month */
const mode = ref<'day' | 'month'>('day')
const month = ref(todayIso().slice(0, 7))
const failed = ref(false)
const exporting = ref(false)
/** The day of the report; the month widgets (sources, ratings) follow the month of that day */
const day = ref(todayIso())
const period = computed(() => (mode.value === 'month' ? month.value : day.value.slice(0, 7)))
const rep = ref<DayReport | null>(null)
const monthOptions = computed(() => Array.from({ length: 13 }, (_, i) => {
  const n = schoolNow()
  const d = new Date(n.getFullYear(), n.getMonth() - i, 1)
  const v = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
  return { value: v, label: periodLabel(v, loc.value) }
}))
type Tile = 'new' | 'contacted' | 'trial' | 'paid' | 'payers' | 'debtors'
const shown = ref<Tile | null>(null)
const modal = ref(false)
const showGone = (k: 'left' | 'frozen' | 'waiting') => router.push({ name: 'dashboard-students', params: { status: k } })
function show(k: Tile) {
  shown.value = k
  modal.value = true
}
const leadTiles = computed(() => (['new', 'trial', 'paid'] as const).map((k) => ({ key: k, icon: { new: 'crm', contacted: 'phone', trial: 'cal', paid: 'ok' }[k], n: rep.value?.leads?.[k].count ?? 0 })))
const leadRows = computed(() => (shown.value && shown.value !== 'payers' && shown.value !== 'debtors' ? rep.value?.leads?.[shown.value].items ?? [] : []))

const SRC: Record<string, { cls: string; icon: string }> = {
  instagram: { cls: 'ig', icon: 'ig' }, whatsapp: { cls: 'wa', icon: 'wa' }, qr: { cls: 'qr', icon: 'qr' }, site: { cls: 'web', icon: 'globe' },
  referral: { cls: 'ref', icon: 'ref' }, sales: { cls: 'call', icon: 'phone' }, return: { cls: 'call', icon: 'lead-return' }, walk_in: { cls: 'call', icon: 'user' },
}

async function load() {
  failed.value = false
  const b = { branch_id: branch.filterId, period: period.value }
  if (!day.value || day.value > todayIso()) day.value = todayIso()
  if (!month.value || month.value > todayIso().slice(0, 7)) month.value = todayIso().slice(0, 7)
  const byMonth = mode.value === 'month'
  financeApi.day({ branch_id: branch.filterId, ...(byMonth ? { month: month.value } : { day: day.value }) }).then((r) => (rep.value = r)).catch(() => (rep.value = null))
  if (auth.can('crm.view')) {
    const [y, m] = month.value.split('-').map(Number)
    const last = `${month.value}-${String(new Date(y ?? 2026, m ?? 1, 0).getDate()).padStart(2, '0')}`
    const from = byMonth ? `${month.value}-01` : day.value
    const to = byMonth ? (last > todayIso() ? todayIso() : last) : day.value
    crmApi.analytics({ date_from: from, date_to: to, branch_id: branch.filterId }).then((r) => (funnel.value = r)).catch(() => (funnel.value = null))
  }
  const [d, r] = await Promise.allSettled([financeApi.dashboard(b), financeApi.ratings(b)])
  if (d.status === 'fulfilled') data.value = d.value
  else failed.value = true
  ratings.value = r.status === 'fulfilled' ? r.value : null
}
onMounted(load)
watch([() => branch.filterId, day, month, mode], load)

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

const sources = computed(() => Object.entries(data.value?.leads_by_source ?? {})
  .map(([k, v]) => ({ key: k, label: srcLabel(k), value: v, icon: SRC[k]?.icon ?? 'user', iconCls: SRC[k]?.cls ?? 'call' }))
  .sort((a, b) => b.value - a.value))
const teacherRows = computed(() => (ratings.value?.teachers ?? []).slice(0, 6))
/** Sales rating: every manager's leads of the period by funnel stage; who sold more stands higher */
const salesRows = computed(() => {
  const st = funnel.value?.stages ?? []
  const won = st.findIndex((x) => x.is_won)
  return [...(funnel.value?.managers ?? [])].sort((a, b) => (b.counts[won] ?? 0) - (a.counts[won] ?? 0) || b.total - a.total)
})

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
    <UiSegmented v-model="mode" :options="[{ value: 'day', label: t('nv.dd.byDay') }, { value: 'month', label: t('nv.dd.byMonth') }]" :label="t('nv.dd.day')" size="sm" />
    <UiInput v-if="mode === 'day'" v-model="day" type="date" :max="todayIso()" :aria-label="t('nv.dd.day')" style="width: 170px" />
    <UiSelect v-else v-model="month" :options="monthOptions" :label="t('nv.dd.byMonth')" />
    <UiButton v-if="auth.can('finance.export')" icon="file" :loading="exporting" @click="exportExcel">{{ t('dash.excel') }}</UiButton>
  </div>

  <UiEmptyState v-if="failed && !data" icon="dash" :title="t('errors.generic')"><UiButton icon="history" @click="load">{{ t('common.retry') }}</UiButton></UiEmptyState>

  <template v-else>
    <div class="kpis stagger">
      <template v-if="!data"><div v-for="i in 6" :key="i" class="card kpi"><UiSkeleton :lines="3" /></div></template>
      <template v-else>
        <template v-if="rep?.leads">
          <template v-for="x in leadTiles" :key="x.key">
            <button type="button" class="card kpi dd-tile" @click="show(x.key)">
              <div class="k"><UiIcon :name="x.icon" :size="18" />{{ t(`nv.dd.${x.key}`) }}</div>
              <div class="v num">{{ num(x.n, loc) }}</div>
              <span class="muted dd-more">{{ t('nv.dd.open') }}</span>
            </button>
          </template>
        </template>
        <button v-if="rep?.payers" type="button" class="card kpi dd-tile" @click="show('payers')">
          <div class="k"><UiIcon name="wallet" :size="18" />{{ t('nv.dd.payers') }}</div>
          <div class="v num">{{ num(rep.payers.count, loc) }}</div>
          <span class="muted dd-more">{{ t('nv.dd.open') }}</span>
        </button>
        <button v-if="rep" type="button" class="card kpi dd-tile" @click="show('debtors')">
          <div class="k"><UiIcon name="alert" :size="18" :style="rep.debtors.count ? { color: 'var(--red)' } : undefined" />{{ t('dash.k.debtors') }}</div>
          <div class="v num">{{ num(rep.debtors.count, loc) }}</div>
          <span class="muted dd-more">{{ t('nv.dd.open') }}</span>
        </button>
        <div class="card kpi">
          <div class="k"><UiIcon name="refusal" :size="18" />{{ t('dash.k.leftPaused') }}</div>
          <div class="kpi-split">
            <button type="button" class="kpi-link" @click="showGone('left')"><b class="v num">{{ num(data.students_left ?? 0, loc) }}</b><span>{{ t('dash.k.left') }}</span></button>
            <button type="button" class="kpi-link" @click="showGone('frozen')"><b class="v num">{{ num(data.students_frozen ?? 0, loc) }}</b><span>{{ t('dash.k.paused') }}</span></button>
            <button type="button" class="kpi-link" @click="showGone('waiting')"><b class="v num">{{ num(data.students_waiting ?? 0, loc) }}</b><span>{{ t('nv.dd.waiting') }}</span></button>
          </div>
          <span class="muted" style="font-size: 12px">{{ t('dash.k.leftMonth', { n: data.left_month ?? 0 }) }}</span>
        </div>
      </template>
    </div>

    <div v-if="data?.leads_by_source" class="grid dash-a">
      <UiCard v-if="data?.leads_by_source" :title="t('dash.sourcesTitle')">
        <template #actions><span class="muted" style="font-size: 12px">{{ t('dash.sourcesNote', { n: data.leads_month ?? 0 }) }}</span></template>
        <HBars v-if="sources.length" :items="sources" />
        <p v-else class="muted m0">{{ t('dash.noLeads') }}</p>
      </UiCard>
    </div>

    <div class="grid">
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

    </div>

    <UiCard v-if="funnel" :title="t('dash.sales')" flush style="margin-top: 16px">
      <div v-if="salesRows.length" class="scroll-x">
        <table class="tbl dd-sales">
          <thead><tr><th>{{ t('dash.r.manager') }}</th><th v-for="st in funnel.stages" :key="st.id" class="r">{{ st.name }}</th></tr></thead>
          <tbody class="num">
            <tr v-for="(r, i) in salesRows" :key="r.user_id ?? 0"><td><span class="rank-n" :class="{ g: i < 3 && r.user_id }">{{ i + 1 }}</span>{{ r.name ?? t('crm.unassigned') }}</td><td v-for="(n, j) in r.counts" :key="j" class="r">{{ n }}</td></tr>
          </tbody>
        </table>
      </div>
      <p v-else class="muted m0 card-pad">{{ t('dash.noSales') }}</p>
    </UiCard>
  </template>

  <UiModal v-model:open="modal" :title="shown ? (shown === 'debtors' ? t('dash.k.debtors') : t(`nv.dd.${shown}`)) : ''">
    <template v-if="rep && shown">
      <template v-if="shown === 'payers'">
        <p v-if="!rep.payers?.items.length" class="muted m0">{{ t('nv.dd.none') }}</p>
        <RouterLink v-for="x in rep.payers?.items ?? []" :key="x.id" :to="`/students/${x.id}`" class="list-row">
          <div class="grow"><b>{{ x.full_name }}</b><span>{{ [x.course ? t('nv.dd.course', { s: money(x.course, loc) }) : '', x.book ? t('nv.dd.book', { s: money(x.book, loc) }) : '', x.other ? t('nv.dd.other', { s: money(x.other, loc) }) : ''].filter(Boolean).join(' · ') }}</span></div>
          <b class="num">{{ money(x.amount, loc) }}</b>
        </RouterLink>
      </template>
      <template v-else-if="shown === 'debtors'">
        <p v-if="!rep.debtors.items.length" class="muted m0">{{ t('nv.dd.none') }}</p>
        <RouterLink v-for="x in rep.debtors.items" :key="x.id" :to="`/students/${x.id}`" class="list-row">
          <div class="grow"><b>{{ x.full_name }}</b><span>{{ refs.branchName(x.branch_id) }}</span></div>
          <UiChip small :tone="x.lessons_left < 0 ? 'red' : 'warn'">{{ t('nv.dd.lessons', { n: x.lessons_left }) }}</UiChip>
        </RouterLink>
      </template>
      <template v-else>
        <p v-if="!leadRows.length" class="muted m0">{{ rep.leads?.[shown].count ? t('nv.dd.hidden') : t('nv.dd.none') }}</p>
        <RouterLink v-for="x in leadRows" :key="x.id" :to="{ path: '/crm', query: { lead: x.id } }" class="list-row">
          <span class="srcico" :class="SRC[x.source]?.cls ?? 'call'"><svg><use :href="`#i-${SRC[x.source]?.icon ?? 'user'}`" /></svg></span>
          <div class="grow"><b>{{ x.full_name }}</b><span>{{ [x.phone ? formatPhone(x.phone) : '', x.manager ?? t('crm.unassigned')].filter(Boolean).join(' · ') }}</span></div>
          <UiChip small>{{ x.stage }}</UiChip>
        </RouterLink>
      </template>
    </template>
  </UiModal>

</template>

<style scoped>
.kpi-link { border: 0; background: none; padding: 0; font: inherit; text-align: left; cursor: pointer }
.dd-tile { text-align: left; font: inherit; color: inherit; cursor: pointer }
.dd-tile:hover { border-color: var(--navy-600) }
.dd-more { font-size: 12px }
.dd-sales { min-width: 820px }
.dd-sales th { white-space: nowrap }
.kpi-split { display: flex; gap: 18px }
.kpi-link { display: grid; color: inherit; text-decoration: none; border-radius: 8px }
.kpi-link span { font-size: 12px; color: var(--muted) }
.kpi-link:hover b { color: var(--red-ink); text-decoration: underline }
</style>
