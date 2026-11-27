<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { UiButton, UiCard, UiChip, UiEmptyState, UiInput, UiModal, UiSegmented, UiSelect, UiSkeleton } from '@/components/ui'
import SourceTiles from '@/components/dashboard/SourceTiles.vue'
import { financeApi, type Dashboard, type DayReport } from '@/api/finance'
import StatTile from '@/components/dashboard/StatTile.vue'
import { crmApi, type Analytics } from '@/api/crm'
import { useAuthStore } from '@/stores/auth'
import { useBranchStore } from '@/stores/branch'
import { useRefsStore } from '@/stores/refs'
import { useSourceLabel } from '@/composables/useSourceLabel'
import { dmy, hm, todayIso, schoolNow } from '@/utils/dates'
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
type Tile = 'new' | 'contacted' | 'trial' | 'paid' | 'debtors' | 'students'
const shown = ref<Tile | null>(null)
const modal = ref(false)
/** The person whose unmarked lessons or overdue tasks are open */
const who = ref<{ kind: 'unmarked' | 'overdue'; id: number } | null>(null)
const whoModal = ref(false)
function showWho(kind: 'unmarked' | 'overdue', id: number) {
  who.value = { kind, id }
  whoModal.value = true
}
const whoLessons = computed(() => (who.value?.kind === 'unmarked' ? rep.value?.unmarked?.items.find((x) => x.id === who.value!.id) : undefined))
const whoTasks = computed(() => (who.value?.kind === 'overdue' ? rep.value?.overdue?.items.find((x) => x.id === who.value!.id) : undefined))
const when = (iso: string) => `${dmy(iso, loc.value)} ${hm(iso, loc.value)}`
const showGone = (k: 'left' | 'frozen' | 'waiting') => router.push({ name: 'dashboard-students', params: { status: k }, query: mode.value === 'month' ? { month: month.value } : { day: day.value } })
/** What the day/month blocks are for: «26.11.2026» or «ноябрь 2026» */
const spanLabel = computed(() => (mode.value === 'month' ? periodLabel(month.value, loc.value) : dmy(day.value, loc.value)))
function show(k: Tile) {
  shown.value = k
  modal.value = true
}
const leadTiles = computed(() => (['new', 'trial', 'paid'] as const).map((k) => ({ key: k, icon: { new: 'crm', contacted: 'phone', trial: 'cal', paid: 'ok' }[k], n: rep.value?.leads?.[k].count ?? 0 })))
const leadKey = computed(() => (shown.value && shown.value !== 'debtors' && shown.value !== 'students' ? shown.value : null))
const leadRows = computed(() => (leadKey.value ? rep.value?.leads?.[leadKey.value].items ?? [] : []))

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
  try {
    data.value = await financeApi.dashboard(b)
  } catch {
    failed.value = true
  }
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

const sources = computed(() => Object.entries(rep.value?.sources ?? {})
  .map(([k, v]) => ({ key: k, label: srcLabel(k), value: v }))
  .sort((a, b) => b.value - a.value))
const sourcesTotal = computed(() => sources.value.reduce((n, x) => n + x.value, 0))
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
    <template v-if="!data || !rep"><div class="dd-row five"><div v-for="i in 5" :key="i" class="card kpi"><UiSkeleton :lines="3" /></div></div></template>
    <template v-else>
      <h2 class="dd-h">{{ t('nv.dd.rowStudents') }}</h2>
      <div class="dd-row five stagger" data-testid="dash-students">
        <StatTile lead icon="graduation" :label="t('nv.dd.active')" :value="rep.students?.active ?? data.students_active ?? 0" :hint="t('nv.dd.now')" @open="router.push({ path: '/students', query: { status: 'active' } })" />
        <StatTile tone="ok" icon="add" :label="t('nv.dd.newStudents')" :value="rep.students?.new.count ?? 0" :hint="spanLabel" @open="show('students')" />
        <StatTile tone="red" icon="refusal" :label="t('dash.k.left')" :value="rep.gone?.left ?? 0" :hint="spanLabel" @open="showGone('left')" />
        <StatTile tone="info" icon="clock" :label="t('dash.k.paused')" :value="rep.gone?.frozen ?? 0" :hint="spanLabel" @open="showGone('frozen')" />
        <StatTile tone="warn" icon="groups" :label="t('nv.dd.waitGroup')" :value="rep.gone?.waiting ?? 0" :hint="t('nv.dd.now')" @open="showGone('waiting')" />
      </div>
      <h2 v-if="rep.leads" class="dd-h">CRM</h2>
      <div v-if="rep.leads" class="dd-row three stagger" data-testid="dash-crm">
        <template v-if="rep.leads">
          <StatTile v-for="x in leadTiles" :key="x.key" :tone="x.key === 'paid' ? 'ok' : 'navy'" :icon="x.icon" :label="t(`nv.dd.${x.key}`)" :value="x.n" :hint="spanLabel" @open="show(x.key)" />
        </template>
      </div>
      <template v-if="rep.unmarked || rep.overdue">
        <h2 class="dd-h">{{ t('nv.dd.rowControl') }}</h2>
        <div class="dd-ctl" data-testid="dash-control">
          <UiCard v-if="rep.unmarked" :title="t('nv.dd.unmarked')" icon="attendance" flush>
            <template #actions><UiChip :tone="rep.unmarked.count ? 'red' : 'ok'">{{ rep.unmarked.count }}</UiChip><span class="muted dd-span">{{ spanLabel }}</span></template>
            <p v-if="!rep.unmarked.items.length" class="muted m0 card-pad">{{ t('nv.dd.unmarkedNone') }}</p>
            <div v-else class="dd-list">
              <button v-for="x in rep.unmarked.items" :key="x.id" type="button" class="list-row pick" @click="showWho('unmarked', x.id)">
                <div class="grow"><b>{{ x.full_name }}</b><span>{{ x.lessons.slice(0, 4).map((l) => `${l.group ?? '—'} ${mode === 'month' ? dmy(l.starts_at, loc).slice(0, 5) + ' ' : ''}${hm(l.starts_at, loc)}`).join(' · ') }}<template v-if="x.lessons.length > 4"> …</template></span></div>
                <UiChip small tone="red">{{ x.lessons.length }}</UiChip>
              </button>
            </div>
          </UiCard>
          <UiCard v-if="rep.overdue" :title="t('nv.dd.overdue')" icon="tasks" flush>
            <template #actions><UiChip :tone="rep.overdue.count ? 'red' : 'ok'">{{ rep.overdue.count }}</UiChip><span class="muted dd-span">{{ t('nv.dd.now') }}</span></template>
            <p v-if="!rep.overdue.items.length" class="muted m0 card-pad">{{ t('nv.dd.overdueNone') }}</p>
            <div v-else class="dd-list">
              <button v-for="x in rep.overdue.items" :key="x.id" type="button" class="list-row pick" @click="showWho('overdue', x.id)">
                <div class="grow"><b>{{ x.full_name }}</b><span>{{ x.tasks[0]?.title }}<template v-if="x.tasks.length > 1"> …</template></span></div>
                <UiChip small tone="red">{{ x.tasks.length }}</UiChip>
              </button>
            </div>
          </UiCard>
        </div>
      </template>
    </template>

    <UiCard v-if="funnel" :title="t('dash.sales')" flush style="margin-bottom: 16px">
      <template #actions><span class="muted" style="font-size: 12px">{{ spanLabel }}</span></template>
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
    <UiCard v-if="rep?.sources" :title="t('dash.sourcesTitle')" style="margin-bottom: 16px" data-testid="dash-sources">
      <template #actions><span class="muted" style="font-size: 12px">{{ spanLabel }} · <b class="num" style="font-size: 15px; color: var(--ink)">{{ num(sourcesTotal, loc) }}</b></span></template>
      <SourceTiles v-if="sources.length" :items="sources" @open="(k) => router.push({ path: '/crm', query: { source: k } })" />
      <p v-else class="muted m0">{{ t('dash.noLeads') }}</p>
    </UiCard>

  </template>

  <UiModal v-model:open="modal" :title="shown ? (shown === 'debtors' ? t('dash.k.debtors') : shown === 'students' ? t('nv.dd.newStudents') : t(`nv.dd.${shown}`)) : ''">
    <template v-if="rep && shown">
      <template v-if="shown === 'debtors'">
        <p v-if="!rep.debtors.items.length" class="muted m0">{{ t('nv.dd.none') }}</p>
        <RouterLink v-for="x in rep.debtors.items" :key="x.id" :to="`/students/${x.id}`" class="list-row">
          <div class="grow"><b>{{ x.full_name }}</b><span>{{ refs.branchName(x.branch_id) }}</span></div>
          <UiChip small :tone="x.lessons_left < 0 ? 'red' : 'warn'">{{ t('nv.dd.lessons', { n: x.lessons_left }) }}</UiChip>
        </RouterLink>
      </template>
      <template v-else-if="shown === 'students'">
        <p v-if="!rep.students?.new.items.length" class="muted m0">{{ t('nv.dd.none') }}</p>
        <RouterLink v-for="x in rep.students?.new.items ?? []" :key="x.id" :to="`/students/${x.id}`" class="list-row">
          <div class="grow"><b>{{ x.full_name }}</b><span>{{ refs.branchName(x.branch_id) }}</span></div>
          <UiChip small>{{ dmy(x.created_on, loc) }}</UiChip>
        </RouterLink>
      </template>
      <template v-else-if="leadKey">
        <p v-if="!leadRows.length" class="muted m0">{{ rep.leads?.[leadKey].count ? t('nv.dd.hidden') : t('nv.dd.none') }}</p>
        <RouterLink v-for="x in leadRows" :key="x.id" :to="{ path: '/crm', query: { lead: x.id } }" class="list-row">
          <span class="srcico" :class="SRC[x.source]?.cls ?? 'call'"><svg><use :href="`#i-${SRC[x.source]?.icon ?? 'user'}`" /></svg></span>
          <div class="grow"><b>{{ x.full_name }}</b><span>{{ [x.phone ? formatPhone(x.phone) : '', x.manager ?? t('crm.unassigned')].filter(Boolean).join(' · ') }}</span></div>
          <UiChip small>{{ x.stage }}</UiChip>
        </RouterLink>
      </template>
    </template>
  </UiModal>

  <UiModal v-model:open="whoModal" :title="(whoLessons ?? whoTasks)?.full_name ?? ''">
    <template v-if="whoLessons">
      <p class="muted" style="margin: 0 0 8px">{{ t('nv.dd.unmarked') }} · {{ t('nv.dd.lessonsN', { n: whoLessons.lessons.length }) }}</p>
      <RouterLink v-for="l in whoLessons.lessons" :key="l.id" :to="`/attendance/${l.id}`" class="list-row">
        <div class="grow"><b>{{ l.group ?? '—' }}</b><span>{{ refs.branchName(l.branch_id) }}</span></div>
        <UiChip small>{{ when(l.starts_at) }}</UiChip>
      </RouterLink>
    </template>
    <template v-else-if="whoTasks">
      <p class="muted" style="margin: 0 0 8px">{{ t('nv.dd.overdue') }} · {{ t('nv.dd.tasksN', { n: whoTasks.tasks.length }) }}</p>
      <RouterLink v-for="x in whoTasks.tasks" :key="x.id" :to="x.lead_id ? { path: '/crm', query: { lead: x.lead_id } } : '/tasks'" class="list-row">
        <div class="grow"><b>{{ x.title }}</b></div>
        <UiChip small tone="red">{{ t('nv.dd.dueWas', { d: when(x.due_at) }) }}</UiChip>
      </RouterLink>
    </template>
  </UiModal>

</template>

<style scoped>
.dd-h { font-size: 12px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); margin: 4px 0 10px }
.dd-row { display: grid; gap: 14px; margin-bottom: 20px }
.dd-row.five { grid-template-columns: repeat(5, minmax(0, 1fr)) }
.dd-row.four { grid-template-columns: repeat(4, minmax(0, 1fr)) }
.dd-row.three { grid-template-columns: repeat(3, minmax(0, 1fr)) }
.dd-ctl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin-bottom: 20px; align-items: start }
.dd-list { max-height: 320px; overflow-y: auto }
.dd-list .list-row { width: 100%; padding-left: 16px; padding-right: 16px }
.dd-span { font-size: 12px; margin-left: 8px }
@media (max-width: 900px) { .dd-ctl { grid-template-columns: minmax(0, 1fr) } }
.dd-sales { min-width: 820px }
.dd-sales th { white-space: nowrap }
@media (max-width: 1100px) { .dd-row.five { grid-template-columns: repeat(3, minmax(0, 1fr)) } .dd-row.four { grid-template-columns: repeat(2, minmax(0, 1fr)) } }
@media (max-width: 640px) { .dd-row.five, .dd-row.four, .dd-row.three { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px } .dd-row.five > :first-child { grid-column: 1 / -1 } }
</style>
