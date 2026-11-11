<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { UiAvatar, UiButton, UiCard, UiChip, UiDrawer, UiEmptyState, UiPeriod, UiPrompt, UiSkeleton, UiTabs } from '@/components/ui'
import AdjustModal from '@/components/ops/AdjustModal.vue'
import { payrollApi, type Accrual, type PayrollPerson, type PayrollSheet, type PeriodStatus } from '@/api/payroll'
import { ApiError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { useBranchStore } from '@/stores/branch'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import { dmy, money } from '@/utils/dates'
import { periodLabel, periodOf } from '@/utils/period'
import type { Locale } from '@/i18n'

const { t, te, locale } = useI18n()
const auth = useAuthStore()
const branch = useBranchStore()
const refs = useRefsStore()
refs.load()
const toast = useToastStore()
const route = useRoute()
const loc = computed(() => locale.value as Locale)

/** Own-scope payroll.view is "my pay" only; branch or network scope also sees the sheet. */
const canSheet = computed(() => auth.can('payroll.view', 'branch'))
type Tab = 'sheet' | 'my'
const tab = ref<Tab>(canSheet.value && route.query.tab !== 'my' ? 'sheet' : 'my')
const tabs = computed(() => [
  ...(canSheet.value ? [{ value: 'sheet' as const, label: t('payroll.tab.sheet') }] : []),
  { value: 'my' as const, label: t('nav.myPay') },
])
const period = ref(periodOf())
const sheet = ref<PayrollSheet | null>(null)
const my = ref<{ total: number; rates_total?: number; salary_total?: number; items: Accrual[] } | null>(null)
const detail = ref<PayrollPerson | null>(null)
const accruals = ref<Accrual[] | null>(null)
const adjustOpen = ref(false)
const adjustFor = ref<number | null>(null)
const confirm = ref<'approve' | 'paid' | null>(null)
const busy = ref(false)
const error = ref<string | null>(null)

const status = computed<PeriodStatus | null>(() => (branch.filterId === null ? null : sheet.value?.status[String(branch.filterId)] ?? 'draft'))
const finished = computed(() => period.value < periodOf())
const locked = computed(() => status.value === 'approved' || status.value === 'paid')

async function loadSheet() {
  if (!canSheet.value) return
  sheet.value = null
  sheet.value = await payrollApi.sheet({ period: period.value, branch_id: branch.filterId }).catch(() => ({ period: period.value, status: {}, people: [], total: 0 }))
}
async function loadMy() {
  my.value = null
  my.value = await payrollApi.my(period.value).catch(() => ({ period: period.value, total: 0, items: [] }))
}
const load = () => (tab.value === 'sheet' ? loadSheet() : loadMy())
onMounted(load)
watch(() => [period.value, branch.filterId, tab.value], load)

async function openPerson(p: PayrollPerson) {
  detail.value = p
  accruals.value = null
  accruals.value = await payrollApi.accruals({ period: period.value, user_id: p.user_id, branch_id: branch.filterId }).catch(() => [])
}
function adjust(userId: number | null) {
  adjustFor.value = userId
  adjustOpen.value = true
}
function afterAdjust() {
  loadSheet()
  if (detail.value) openPerson(detail.value)
}
async function runConfirm() {
  const id = branch.filterId
  if (!id || !confirm.value) return
  busy.value = true
  error.value = null
  try {
    if (confirm.value === 'approve') await payrollApi.approve(period.value, id)
    else await payrollApi.paid(period.value, id)
    toast.ok(confirm.value === 'approve' ? t('payroll.approved') : t('payroll.markedPaid'))
    confirm.value = null
    loadSheet()
  } catch (e) {
    error.value = e instanceof ApiError ? e.detail || t('errors.generic') : t('errors.generic')
  } finally {
    busy.value = false
  }
}
const kindLabel = (k: string) => (te(`payroll.kind.${k}`) ? t(`payroll.kind.${k}`) : k)
const topKinds = (p: PayrollPerson) => Object.entries(p.by_kind).sort((a, b) => Math.abs(b[1].amount) - Math.abs(a[1].amount)).slice(0, 3)
const signed = (n: number) => (n > 0 ? `+${money(n, loc.value)}` : n < 0 ? `−${money(-n, loc.value)}` : money(0, loc.value))
</script>

<template>
  <div class="ph">
    <div><h1>{{ t('nav.payroll') }}</h1><p>{{ t('payroll.subtitle') }}</p></div>
    <span class="sp" />
    <UiButton v-if="tab === 'sheet' && auth.can('payroll.adjust')" icon="plus" :disabled="locked" :title="locked ? t('payroll.lockedNote') : undefined" @click="adjust(null)">{{ t('payroll.adjust') }}</UiButton>
  </div>

  <div class="toolbar">
    <UiPeriod v-model="period" />
    <UiTabs v-if="tabs.length > 1" v-model="tab" :items="tabs" :label="t('nav.payroll')" />
  </div>

  <template v-if="tab === 'sheet'">
    <div v-if="branch.filterId === null" class="alert info">
      <div class="grow">
        <span>{{ t('payroll.pickBranch') }}</span>
        <div v-if="sheet && Object.keys(sheet.status).length" class="chips-row" style="margin-top: 8px">
          <UiChip v-for="(st, id) in sheet.status" :key="id" small :tone="st === 'paid' ? 'ok' : st === 'approved' ? 'info' : undefined">{{ refs.branchName(Number(id)) }} · {{ t(`payroll.status.${st}`) }}</UiChip>
        </div>
      </div>
    </div>
    <div v-else-if="sheet && status" class="alert" :class="status === 'paid' ? 'ok' : status === 'approved' ? 'info' : ''">
      <div class="grow">
        <b>{{ t(`payroll.status.${status}`) }} · {{ periodLabel(period, loc) }}</b>
        <span>{{ status === 'draft' ? (finished ? t('payroll.draftNote') : t('payroll.openNote')) : status === 'approved' ? t('payroll.approvedNote') : t('payroll.paidNote') }}</span>
      </div>
      <template v-if="auth.can('payroll.approve')">
        <UiButton v-if="status === 'draft'" size="sm" variant="navy" icon="ok" :disabled="!finished" :title="!finished ? t('payroll.onlyFinished') : undefined" @click="confirm = 'approve'">{{ t('payroll.approve') }}</UiButton>
        <UiButton v-else-if="status === 'approved'" size="sm" variant="primary" icon="wallet" @click="confirm = 'paid'">{{ t('payroll.markPaid') }}</UiButton>
      </template>
    </div>

    <UiCard flush>
      <template #header><h3>{{ t('payroll.sheetTitle') }}</h3></template>
      <template #actions><b v-if="sheet" class="num">{{ money(sheet.total, loc) }}</b></template>
      <div v-if="!sheet" class="card-pad"><UiSkeleton :lines="5" /></div>
      <div v-else-if="sheet.people.length" class="card-b lr-list">
        <button v-for="p in sheet.people" :key="p.user_id" type="button" class="list-row pick" @click="openPerson(p)">
          <UiAvatar :name="p.full_name" />
          <div class="grow">
            <b>{{ p.full_name }}</b>
            <span>{{ p.position ?? '—' }}<template v-if="p.salary_total"> · {{ t('payroll.bySalary') }} {{ money(p.salary_total, loc) }} · {{ t('payroll.byRates') }} {{ money(p.rates_total, loc) }}</template><template v-else><template v-for="[k, v] in topKinds(p)" :key="k"> · {{ kindLabel(String(k)) }} {{ money(v.amount, loc) }}</template></template></span>
          </div>
          <b class="num">{{ money(p.total, loc) }}</b>
        </button>
      </div>
      <UiEmptyState v-else icon="salary" :title="t('payroll.empty')" />
    </UiCard>
  </template>

  <template v-else>
    <div class="grid fin-k">
      <div class="card kpi">
        <div class="k">{{ t('payroll.myTotal', { period: periodLabel(period, loc) }) }}</div>
        <div v-if="my" class="v num">{{ money(my.total, loc) }}</div><UiSkeleton v-else :lines="1" />
        <span v-if="my && my.salary_total" class="muted" style="font-size: 12px">{{ t('payroll.bySalary') }} {{ money(my.salary_total, loc) }} · {{ t('payroll.byRates') }} {{ money(my.rates_total ?? 0, loc) }}</span>
        <span class="muted" style="font-size: 12px">{{ t('payroll.myNote') }}</span>
      </div>
    </div>
    <UiCard :title="t('payroll.lines')" flush>
      <div v-if="!my" class="card-pad"><UiSkeleton :lines="5" /></div>
      <div v-else-if="my.items.length" class="card-b lr-list">
        <div v-for="a in my.items" :key="a.id" class="list-row">
          <div class="grow"><b>{{ kindLabel(a.kind) }}</b><span>{{ a.description }} · {{ dmy(a.created_at, loc) }}</span></div>
          <b class="num" :class="a.amount < 0 ? 'redc' : 'okc'">{{ signed(a.amount) }}</b>
        </div>
      </div>
      <UiEmptyState v-else icon="salary" :title="t('payroll.myEmpty')" />
    </UiCard>
  </template>

  <UiDrawer :open="detail !== null" :title="detail?.full_name ?? ''" @update:open="(v) => !v && (detail = null)">
    <template v-if="detail">
      <div class="stack">
        <div class="muted">{{ detail.position ?? '' }} · {{ periodLabel(period, loc) }}</div>
        <div class="kv-grid">
          <template v-for="(v, k) in detail.by_kind" :key="k"><span>{{ kindLabel(String(k)) }} <span class="muted">× {{ v.count }}</span></span><b class="num">{{ money(v.amount, loc) }}</b></template>
          <template v-if="detail.salary_total">
            <span class="muted">{{ t('payroll.bySalary') }}</span><b class="num">{{ money(detail.salary_total, loc) }}</b>
            <span class="muted">{{ t('payroll.byRates') }}</span><b class="num">{{ money(detail.rates_total, loc) }}</b>
          </template>
          <span><b>{{ t('fin.total') }}</b></span><b class="num">{{ money(detail.total, loc) }}</b>
        </div>
        <h4 class="m0">{{ t('payroll.lines') }}</h4>
        <UiSkeleton v-if="!accruals" :lines="4" />
        <div v-else class="lr-list">
          <div v-for="a in accruals" :key="a.id" class="list-row">
            <div class="grow"><b>{{ kindLabel(a.kind) }}</b><span>{{ a.description }} · {{ dmy(a.created_at, loc) }}</span></div>
            <b class="num" :class="a.amount < 0 ? 'redc' : undefined">{{ signed(a.amount) }}</b>
          </div>
        </div>
      </div>
    </template>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.close') }}</UiButton>
      <UiButton v-if="auth.can('payroll.adjust') && detail?.user_id !== auth.user?.id" variant="navy" icon="plus" :disabled="locked" @click="adjust(detail?.user_id ?? null)">{{ t('payroll.adjust') }}</UiButton>
    </template>
  </UiDrawer>

  <AdjustModal v-model:open="adjustOpen" :period="period" :user-id="adjustFor" @saved="afterAdjust" />
  <UiPrompt
    :open="confirm !== null"
    :title="confirm === 'approve' ? t('payroll.approveTitle', { period: periodLabel(period, loc) }) : t('payroll.paidTitle', { period: periodLabel(period, loc) })"
    :text="confirm === 'approve' ? t('payroll.approveText', { sum: money(sheet?.total ?? 0, loc) }) : t('payroll.paidText')"
    :confirm-label="confirm === 'approve' ? t('payroll.approve') : t('payroll.markPaid')"
    :busy="busy"
    :error="error"
    @update:open="(v) => !v && ((confirm = null), (error = null))"
    @confirm="runConfirm"
  />
</template>
