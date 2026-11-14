<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiCard, UiChip, UiEmptyState, UiInput, UiPager, UiPeriod, UiPrompt, UiSelect, UiSkeleton, UiTable, UiTabs, type TableColumn } from '@/components/ui'
import HBars from '@/components/charts/HBars.vue'
import ExpenseDrawer from '@/components/ops/ExpenseDrawer.vue'
import { financeApi, type Expense, type ExpenseCategory, type Pnl } from '@/api/finance'
import { useAuthStore } from '@/stores/auth'
import { useBranchStore } from '@/stores/branch'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import { dmy, money, todayIso } from '@/utils/dates'
import { num, periodLabel, periodOf } from '@/utils/period'
import type { Locale } from '@/i18n'

const LIMIT = 30
const { t, te, locale } = useI18n()
const auth = useAuthStore()
const branch = useBranchStore()
const refs = useRefsStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)

type Tab = 'pnl' | 'expenses'
const tab = ref<Tab>('pnl')
const period = ref(periodOf())
const pnl = ref<Pnl | null>(null)
const categories = ref<ExpenseCategory[]>([])
const expenses = ref<Expense[]>([])
const total = ref(0)
const offset = ref(0)
const catFilter = ref(0)
const expLoading = ref(true)
const drawer = ref(false)
const editing = ref<Expense | null>(null)
const archiving = ref<Expense | null>(null)
const busy = ref(false)
const exporting = ref<'payments' | 'pnl' | null>(null)

const tabs = computed(() => [{ value: 'pnl' as const, label: t('fin.tab.pnl') }, { value: 'expenses' as const, label: t('fin.tab.expenses'), count: total.value || undefined }])
const catName = (id: number) => categories.value.find((c) => c.id === id)?.name ?? `#${id}`
const catOptions = computed(() => [{ value: 0, label: t('fin.allCategories') }, ...categories.value.map((c) => ({ value: c.id, label: c.name }))])
/** Any range of days instead of the month: filled dates win over the month stepper. */
const range = ref({ from: '', to: '' })
const ranged = computed(() => Boolean(range.value.from || range.value.to))
const dates = computed(() => ({ date_from: range.value.from || null, date_to: range.value.to || null }))
const rangeLabel = computed(() => {
  const { from, to } = range.value
  if (from && to) return `${dmy(from, loc.value)} – ${dmy(to, loc.value)}`
  return from ? t('nv.fin.since', { d: dmy(from, loc.value) }) : t('nv.fin.until', { d: dmy(to, loc.value) })
})

async function loadPnl() {
  pnl.value = null
  pnl.value = await financeApi.pnl({ period: period.value, branch_id: branch.filterId, ...dates.value }).catch(() => null)
}
let seq = 0
async function loadExpenses() {
  const my = ++seq
  expLoading.value = true
  try {
    const page = await financeApi.expenses({ period: period.value, branch_id: branch.filterId, ...dates.value, category_id: catFilter.value || null, limit: LIMIT, offset: offset.value })
    if (my !== seq) return
    expenses.value = page.items
    total.value = page.total
  } catch {
    if (my === seq) expenses.value = []
  } finally {
    if (my === seq) expLoading.value = false
  }
}
function reload() {
  loadPnl()
  offset.value === 0 ? loadExpenses() : (offset.value = 0)
}
onMounted(async () => {
  categories.value = await financeApi.categories().catch(() => [])
  reload()
})
watch(() => [period.value, branch.filterId, catFilter.value, range.value.from, range.value.to], reload)
watch(offset, loadExpenses)

const totals = computed(() => pnl.value?.total)
const byCategory = computed(() => {
  const acc = new Map<string, number>()
  for (const r of pnl.value?.branches ?? []) for (const [k, v] of Object.entries(r.expenses)) acc.set(k, (acc.get(k) ?? 0) + v)
  const payroll = totals.value?.payroll ?? 0
  const rows = [...acc.entries()].map(([k, v]) => ({ key: k, label: k, value: v }))
  if (payroll) rows.push({ key: '__payroll', label: t('fin.payroll'), value: payroll })
  return rows.sort((a, b) => b.value - a.value)
})
const revenueCats = computed(() => {
  const acc = new Map<string, number>()
  for (const r of pnl.value?.branches ?? []) for (const [k, v] of Object.entries(r.net_by_category ?? r.revenue)) acc.set(k, (acc.get(k) ?? 0) + v)
  return [...acc.entries()].map(([k, v]) => ({ key: k, label: te(`fin.revCat.${k}`) ? t(`fin.revCat.${k}`) : k, value: v })).sort((a, b) => b.value - a.value)
})
const marginLabel = (m: number | null) => (m === null ? '—' : `${num(m, loc.value, 1)}%`)

const columns = computed<TableColumn[]>(() => [
  { key: 'spent_on', label: t('students.col.date') },
  { key: 'category_id', label: t('fin.category') },
  { key: 'branch_id', label: t('branch.label') },
  { key: 'note', label: t('fin.note') },
  { key: 'amount', label: t('fin.amount'), align: 'right' },
  { key: 'actions', label: '', align: 'right' },
])

function openNew() {
  editing.value = null
  drawer.value = true
}
function edit(e: Expense) {
  editing.value = e
  drawer.value = true
}
async function archive() {
  const e = archiving.value
  if (!e) return
  busy.value = true
  try {
    await financeApi.archiveExpense(e.id)
    toast.ok(t('fin.archived'))
    archiving.value = null
    reload()
  } finally {
    busy.value = false
  }
}
async function exportFile(kind: 'payments' | 'pnl') {
  exporting.value = kind
  try {
    const p = { period: period.value, branch_id: branch.filterId }
    await (kind === 'payments' ? financeApi.exportPayments(p) : financeApi.exportPnl(p))
  } catch {
    /* toast */
  } finally {
    exporting.value = null
  }
}
</script>

<template>
  <div class="ph">
    <div><h1>{{ t('fin.title') }}</h1><p>{{ ranged ? rangeLabel : periodLabel(period, loc) }} · {{ branch.filterId === null ? t('branch.all') : branch.current.name }}</p></div>
    <span class="sp" />
    <template v-if="auth.can('finance.export') && !ranged">
      <UiButton icon="dl" :loading="exporting === 'pnl'" @click="exportFile('pnl')">{{ t('fin.exportPnl') }}</UiButton>
      <UiButton icon="dl" :loading="exporting === 'payments'" @click="exportFile('payments')">{{ t('fin.exportPayments') }}</UiButton>
    </template>
    <UiButton v-if="auth.can('finance.edit')" variant="primary" icon="plus" @click="openNew">{{ t('fin.expense') }}</UiButton>
  </div>

  <div class="toolbar">
    <UiPeriod v-if="!ranged" v-model="period" />
    <UiInput v-model="range.from" type="date" :max="range.to || todayIso()" class="tb-date" :aria-label="t('payments.from')" />
    <span class="muted">—</span>
    <UiInput v-model="range.to" type="date" :min="range.from" :max="todayIso()" class="tb-date" :aria-label="t('payments.to')" />
    <UiButton v-if="ranged" size="sm" variant="ghost" icon="x" @click="range = { from: '', to: '' }">{{ t('nv.fin.byMonth') }}</UiButton>
    <UiTabs v-model="tab" :items="tabs" :label="t('fin.title')" class="tb-tabs" />
  </div>

  <template v-if="tab === 'pnl'">
    <div class="grid fin-k stagger" style="grid-template-columns: repeat(auto-fit, minmax(220px, 1fr))">
      <template v-if="!totals"><div v-for="i in 3" :key="i" class="card kpi"><UiSkeleton :lines="3" /></div></template>
      <template v-else>
        <div class="card kpi"><div class="k">{{ t('fin.gross') }}</div><div class="v num">{{ money(totals.receipts, loc) }}</div><span class="muted" style="font-size: 12px">{{ totals.refunds ? t('nv.fin.refundsNet', { refunds: money(totals.refunds, loc), net: money(totals.net_revenue, loc) }) : t('fin.noRefunds') }}</span></div>
        <div class="card kpi"><div class="k">{{ t('fin.expenses') }}</div><div class="v num">{{ money(totals.total_expenses, loc) }}</div><span class="muted" style="font-size: 12px">{{ t('fin.payrollNote', { sum: money(totals.payroll, loc) }) }}</span></div>
        <div class="card kpi"><div class="k">{{ t('fin.profit') }}</div><div class="v num" :class="{ redc: totals.profit < 0 }">{{ money(totals.profit, loc) }}</div><span class="muted" style="font-size: 12px">{{ t('fin.margin', { m: marginLabel(totals.margin) }) }}</span></div>
      </template>
    </div>

    <div class="grid fin-a">
      <UiCard :title="t('fin.pnlByBranch')" flush>
        <div v-if="!pnl" class="card-pad"><UiSkeleton :lines="4" /></div>
        <div v-else class="scroll-x">
          <table class="tbl" style="min-width: 560px">
            <thead><tr><th>{{ t('branch.label') }}</th><th class="r">{{ t('nv.fin.netRevenue') }}</th><th class="r">{{ t('fin.payroll') }}</th><th class="r">{{ t('fin.expenses') }}</th><th class="r">{{ t('fin.profit') }}</th><th class="r">{{ t('fin.marginCol') }}</th></tr></thead>
            <tbody class="num">
              <tr v-for="r in pnl.branches" :key="r.branch_id">
                <td><b>{{ r.branch }}</b><div v-if="r.refunds" class="muted" style="font-size: 12px">{{ t('fin.refundsNote', { sum: money(r.refunds, loc) }) }}</div></td>
                <td class="r">{{ money(r.net_revenue, loc) }}</td>
                <td class="r">{{ money(r.payroll, loc) }}</td>
                <td class="r">{{ money(r.total_expenses, loc) }}</td>
                <td class="r" :class="{ redc: r.profit < 0 }">{{ money(r.profit, loc) }}</td>
                <td class="r">{{ marginLabel(r.margin) }}</td>
              </tr>
              <tr v-if="pnl.branches.length > 1" class="tot">
                <td><b>{{ t('fin.total') }}</b></td>
                <td class="r"><b>{{ money(pnl.total.net_revenue, loc) }}</b></td>
                <td class="r"><b>{{ money(pnl.total.payroll, loc) }}</b></td>
                <td class="r"><b>{{ money(pnl.total.total_expenses, loc) }}</b></td>
                <td class="r" :class="{ redc: pnl.total.profit < 0 }"><b>{{ money(pnl.total.profit, loc) }}</b></td>
                <td class="r"><b>{{ marginLabel(pnl.total.margin) }}</b></td>
              </tr>
            </tbody>
          </table>
        </div>
      </UiCard>
      <div class="grid" style="align-content: start; grid-template-columns: minmax(0, 1fr)">
        <UiCard :title="t('nv.fin.netByCat')">
          <UiSkeleton v-if="!pnl" :lines="3" />
          <HBars v-else-if="revenueCats.length" :items="revenueCats" :format="(v) => money(v, loc)" />
          <p v-else class="muted m0">{{ t('fin.noRevenue') }}</p>
        </UiCard>
        <UiCard :title="t('fin.expensesByCat')">
          <UiSkeleton v-if="!pnl" :lines="3" />
          <HBars v-else-if="byCategory.length" :items="byCategory" :format="(v) => money(v, loc)" />
          <p v-else class="muted m0">{{ t('fin.noExpenses') }}</p>
        </UiCard>
      </div>
    </div>
  </template>

  <template v-else>
    <div class="toolbar">
      <UiSelect v-model="catFilter" :options="catOptions" :label="t('fin.category')" />
    </div>
    <UiCard flush>
      <UiTable :columns="columns" :rows="expenses" :loading="expLoading">
        <template #cell-spent_on="{ row }"><span class="num">{{ dmy(row.spent_on as string, loc) }}</span></template>
        <template #cell-category_id="{ row }">
          {{ catName(row.category_id as number) }}
          <UiChip v-if="row.recurring" tone="info" small icon="history">{{ t('fin.monthly', { d: row.recurring_day }) }}</UiChip>
          <UiChip v-if="row.source_ref" small>{{ t('fin.auto') }}</UiChip>
        </template>
        <template #cell-branch_id="{ row }"><span class="muted">{{ row.branch_id ? refs.branchName(row.branch_id as number) : t('fin.network') }}</span></template>
        <template #cell-note="{ row }"><span class="muted">{{ row.note ?? '—' }}</span></template>
        <template #cell-amount="{ row }"><b class="num">{{ money(row.amount as number, loc) }}</b></template>
        <template #cell-actions="{ row }">
          <template v-if="auth.can('finance.edit') && !row.source_ref">
            <UiButton size="sm" variant="ghost" icon="edit" :aria-label="t('common.edit')" :title="t('common.edit')" @click="edit(row as Expense)" />
            <UiButton size="sm" variant="ghost" icon="archive" :aria-label="t('fin.archive')" :title="t('fin.archive')" @click="archiving = row as Expense" />
          </template>
        </template>
        <template #empty><UiEmptyState icon="wallet" :title="t('fin.noExpensesPeriod')" /></template>
      </UiTable>
      <UiPager v-model="offset" :total="total" :limit="LIMIT" />
    </UiCard>
  </template>

  <ExpenseDrawer v-model:open="drawer" :expense="editing" :categories="categories" @saved="reload" @category-added="(c) => categories.push(c)" />
  <UiPrompt :open="archiving !== null" :title="t('fin.archiveTitle')" :text="archiving ? `${catName(archiving.category_id)} · ${money(archiving.amount, loc)}` : ''" :confirm-label="t('fin.archive')" danger :busy="busy" @update:open="(v) => !v && (archiving = null)" @confirm="archive" />
</template>
