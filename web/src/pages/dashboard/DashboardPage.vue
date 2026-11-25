<script setup lang="ts">
import { nowMs } from '@/utils/clock'
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiCard, UiChip, UiEmptyState, UiIcon, UiInput, UiModal, UiSkeleton } from '@/components/ui'
import HBars from '@/components/charts/HBars.vue'
import { financeApi, type Dashboard, type DayReport, type Ratings } from '@/api/finance'
import { academicsApi, type Lesson } from '@/api/academics'
import { crmApi, type Lead } from '@/api/crm'
import { useAuthStore } from '@/stores/auth'
import { useBranchStore } from '@/stores/branch'
import { useRefsStore } from '@/stores/refs'
import { useSourceLabel } from '@/composables/useSourceLabel'
import { hm, isoDate, money, todayIso, waitLabel, schoolNow } from '@/utils/dates'
import { num, periodLabel } from '@/utils/period'
import { formatPhone } from '@/utils/phone'
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
/** The day of the report; the month widgets (sources, ratings) follow the month of that day */
const day = ref(todayIso())
const period = computed(() => day.value.slice(0, 7))
const rep = ref<DayReport | null>(null)
type Tile = 'new' | 'contacted' | 'trial' | 'paid' | 'payers' | 'debtors'
const shown = ref<Tile | null>(null)
const modal = ref(false)
function show(k: Tile) {
  shown.value = k
  modal.value = true
}
const leadTiles = computed(() => (['new', 'contacted', 'trial', 'paid'] as const).map((k) => ({ key: k, icon: { new: 'crm', contacted: 'phone', trial: 'cal', paid: 'ok' }[k], n: rep.value?.leads?.[k].count ?? 0 })))
const leadRows = computed(() => (shown.value && shown.value !== 'payers' && shown.value !== 'debtors' ? rep.value?.leads?.[shown.value].items ?? [] : []))

const SRC: Record<string, { cls: string; icon: string }> = {
  instagram: { cls: 'ig', icon: 'ig' }, whatsapp: { cls: 'wa', icon: 'wa' }, qr: { cls: 'qr', icon: 'qr' }, site: { cls: 'web', icon: 'globe' },
  referral: { cls: 'ref', icon: 'ref' }, sales: { cls: 'call', icon: 'phone' }, return: { cls: 'call', icon: 'lead-return' }, walk_in: { cls: 'call', icon: 'user' },
}

async function load() {
  failed.value = false
  const b = { branch_id: branch.filterId, period: period.value }
  if (!day.value || day.value > todayIso()) day.value = todayIso()
  financeApi.day({ branch_id: branch.filterId, day: day.value }).then((r) => (rep.value = r)).catch(() => (rep.value = null))
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
watch([() => branch.filterId, day], load)

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

const sources = computed(() => Object.entries(data.value?.leads_by_source ?? {})
  .map(([k, v]) => ({ key: k, label: srcLabel(k), value: v, icon: SRC[k]?.icon ?? 'user', iconCls: SRC[k]?.cls ?? 'call' }))
  .sort((a, b) => b.value - a.value))
const upcoming = computed(() => {
  const now = nowMs()
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
    <UiInput v-model="day" type="date" :max="todayIso()" :aria-label="t('nv.dd.day')" style="width: 170px" />
    <UiButton v-if="auth.can('finance.export')" icon="file" :loading="exporting" @click="exportExcel">{{ t('dash.excel') }}</UiButton>
  </div>

  <UiEmptyState v-if="failed && !data" icon="dash" :title="t('errors.generic')"><UiButton icon="history" @click="load">{{ t('common.retry') }}</UiButton></UiEmptyState>

  <template v-else>
    <div class="kpis stagger">
      <template v-if="!data"><div v-for="i in 6" :key="i" class="card kpi"><UiSkeleton :lines="3" /></div></template>
      <template v-else>
        <template v-if="rep?.leads">
          <button v-for="x in leadTiles" :key="x.key" type="button" class="card kpi dd-tile" @click="show(x.key)">
            <div class="k"><UiIcon :name="x.icon" :size="18" />{{ t(`nv.dd.${x.key}`) }}</div>
            <div class="v num">{{ num(x.n, loc) }}</div>
            <span class="muted dd-more">{{ t('nv.dd.open') }}</span>
          </button>
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
            <RouterLink :to="{ path: '/students', query: { status: 'left' } }" class="kpi-link"><b class="v num">{{ num(data.students_left ?? 0, loc) }}</b><span>{{ t('dash.k.left') }}</span></RouterLink>
            <RouterLink :to="{ path: '/students', query: { status: 'frozen' } }" class="kpi-link"><b class="v num">{{ num(data.students_frozen ?? 0, loc) }}</b><span>{{ t('dash.k.paused') }}</span></RouterLink>
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
.dd-tile { text-align: left; font: inherit; color: inherit; cursor: pointer }
.dd-tile:hover { border-color: var(--navy-600) }
.dd-more { font-size: 12px }
.kpi-split { display: flex; gap: 18px }
.kpi-link { display: grid; color: inherit; text-decoration: none; border-radius: 8px }
.kpi-link span { font-size: 12px; color: var(--muted) }
.kpi-link:hover b { color: var(--red-ink); text-decoration: underline }
</style>
