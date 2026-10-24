<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiAvatar, UiButton, UiCard, UiChip, UiEmptyState, UiInput, UiPager, UiTable, type TableColumn } from '@/components/ui'
import RefundModal from '@/components/students/RefundModal.vue'
import { paymentsApi, type Payment } from '@/api/payments'
import { useAuthStore } from '@/stores/auth'
import { useBranchStore } from '@/stores/branch'
import { useRefsStore } from '@/stores/refs'
import { addDays, dmy, hm, isoDate, money } from '@/utils/dates'
import type { Locale } from '@/i18n'

const LIMIT = 30
const { t, locale } = useI18n()
const auth = useAuthStore()
const branch = useBranchStore()
const refs = useRefsStore()
const loc = computed(() => locale.value as Locale)

const today = new Date()
const f = reactive({ from: isoDate(new Date(today.getFullYear(), today.getMonth(), 1)), to: isoDate(today), offset: 0 })
const rows = ref<Payment[]>([])
const total = ref(0)
const loading = ref(true)
const refundOf = ref<Payment | null>(null)
let seq = 0

const columns = computed<TableColumn[]>(() => [
  { key: 'paid_at', label: t('students.col.date') },
  { key: 'student_name', label: t('payments.col.student') },
  { key: 'amount', label: t('payments.col.amount'), align: 'right' },
  { key: 'method', label: t('payments.col.method') },
  { key: 'branch_id', label: t('branch.label') },
  { key: 'actions', label: '', align: 'right' },
])
const pageSum = computed(() => rows.value.reduce((a, p) => a + p.amount - p.refunded, 0))

async function load() {
  const my = ++seq
  loading.value = true
  try {
    const page = await paymentsApi.list({ branch_id: branch.filterId, date_from: f.from || undefined, date_to: f.to || undefined, limit: LIMIT, offset: f.offset })
    if (my !== seq) return
    rows.value = page.items
    total.value = page.total
  } catch {
    if (my === seq) rows.value = []
  } finally {
    if (my === seq) loading.value = false
  }
}

watch(() => [f.from, f.to, branch.filterId], () => (f.offset === 0 ? load() : (f.offset = 0)))
watch(() => f.offset, load)
onMounted(load)

function preset(days: number | 'month') {
  const now = new Date()
  f.to = isoDate(now)
  f.from = days === 'month' ? isoDate(new Date(now.getFullYear(), now.getMonth(), 1)) : isoDate(addDays(now, -days + 1))
}
const canRefund = (p: Payment) => auth.can('payments.refund') && p.refunded < p.amount
const methodIco = (m: string) => (m === 'kaspi' ? 'K' : m === 'cash' ? '₸' : '▭')
</script>

<template>
  <div class="ph">
    <div><h1>{{ t('payments.title') }}</h1><p>{{ t('payments.subtitle', { n: total }) }}</p></div>
  </div>

  <div class="toolbar">
    <UiInput v-model="f.from" type="date" :max="f.to" class="tb-date" :aria-label="t('payments.from')" />
    <span class="muted">—</span>
    <UiInput v-model="f.to" type="date" :min="f.from" class="tb-date" :aria-label="t('payments.to')" />
    <button type="button" class="tgl" @click="preset(1)">{{ t('payments.today') }}</button>
    <button type="button" class="tgl" @click="preset(7)">{{ t('payments.week') }}</button>
    <button type="button" class="tgl" @click="preset('month')">{{ t('payments.month') }}</button>
    <span class="sp" />
    <span v-if="rows.length" class="muted num">{{ t('payments.pageSum') }}: <b class="ink">{{ money(pageSum, loc) }}</b></span>
  </div>

  <UiCard flush>
    <UiTable :columns="columns" :rows="rows as unknown as Record<string, unknown>[]" :loading="loading">
      <template #cell-paid_at="{ row }"><span class="num">{{ dmy(row.paid_at as string, loc) }}</span> <span class="muted num">{{ hm(row.paid_at as string, loc) }}</span></template>
      <template #cell-student_name="{ row }">
        <RouterLink v-if="auth.can('students.view')" :to="{ name: 'student', params: { id: row.student_id as number } }" class="who2 rowlink">
          <UiAvatar :name="(row.student_name as string) ?? '?'" size="sm" /><span>{{ row.student_name }}</span>
        </RouterLink>
        <span v-else>{{ row.student_name }}</span>
        <UiChip v-if="row.is_first" tone="info" small>{{ t('payments.first') }}</UiChip>
      </template>
      <template #cell-amount="{ row }">
        <b class="num">{{ money(row.amount as number, loc) }}</b>
        <div class="muted" style="font-size: 12px">
          {{ t('students.nLessons', { n: row.lessons }) }}
          <template v-if="(row.discount as number) > 0"> · −{{ money(row.discount as number, loc) }}</template>
          <template v-if="(row.refunded as number) > 0"> · <span class="redc">{{ t('payments.refunded', { sum: money(row.refunded as number, loc) }) }}</span></template>
        </div>
      </template>
      <template #cell-method="{ row }">
        <span class="method"><i :class="row.method === 'kaspi' && 'kaspi'" :style="row.method !== 'kaspi' ? { background: `var(--${row.method === 'cash' ? 'ok' : 'info'})` } : undefined">{{ methodIco(row.method as string) }}</i>{{ t(`payments.method.${row.method}`) }}</span>
      </template>
      <template #cell-branch_id="{ row }"><span class="muted">{{ refs.branchName(row.branch_id as number) }}</span></template>
      <template #cell-actions="{ row }">
        <UiButton v-if="canRefund(row as unknown as Payment)" size="sm" variant="ghost" icon="history" @click="refundOf = row as unknown as Payment">{{ t('payments.refund') }}</UiButton>
      </template>
      <template #empty><UiEmptyState icon="wallet" :title="t('payments.empty')" /></template>
    </UiTable>
    <UiPager v-model="f.offset" :total="total" :limit="LIMIT" />
  </UiCard>

  <RefundModal :payment="refundOf" @close="refundOf = null" @done="load" />
</template>
