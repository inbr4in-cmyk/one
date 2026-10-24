<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { UiButton, UiCard, UiChip, UiEmptyState, UiPeriod, UiSkeleton, UiTabs } from '@/components/ui'
import LevelTag from '@/components/students/LevelTag.vue'
import BookModal from '@/components/store/BookModal.vue'
import StockModal, { type StockMode } from '@/components/store/StockModal.vue'
import { booksApi, type Book, type BooksReport, type BookTransfer } from '@/api/store'
import { useAuthStore } from '@/stores/auth'
import { useBranchStore } from '@/stores/branch'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import { dmy, money } from '@/utils/dates'
import { periodLabel, periodOf } from '@/utils/period'
import type { Locale } from '@/i18n'

type Tab = 'catalog' | 'transfers' | 'report'
const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const branch = useBranchStore()
const refs = useRefsStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)

const books = ref<Book[] | null>(null)
const transfers = ref<BookTransfer[] | null>(null)
const report = ref<BooksReport | null>(null)
const period = ref(periodOf())
const q = ref('')
const editing = ref<Book | null>(null)
const bookModal = ref(false)
const stock = ref<{ book: Book; mode: StockMode } | null>(null)
const confirming = ref<number | null>(null)

const canStock = computed(() => auth.can('books.stock'))
const tab = computed<Tab>({
  get: () => {
    const v = route.params.tab
    return canStock.value && (v === 'transfers' || v === 'report') ? v : 'catalog'
  },
  set: (v) => void router.replace({ path: v === 'catalog' ? '/books' : `/books/${v}` }),
})
const myBranchIds = computed(() => new Set(branch.options.map((o) => o.id).filter((x): x is number => x !== null)))
const incoming = computed(() => transfers.value?.filter((x) => myBranchIds.value.has(x.to_branch_id)) ?? [])
const outgoing = computed(() => transfers.value?.filter((x) => !myBranchIds.value.has(x.to_branch_id)) ?? [])
const tabs = computed(() => [
  { value: 'catalog' as const, label: t('books.tab.catalog') },
  ...(canStock.value ? [{ value: 'transfers' as const, label: t('books.tab.transfers'), count: incoming.value.length || undefined }, { value: 'report' as const, label: t('books.tab.report') }] : []),
])

/** Branch columns: the selected branch, or every branch the user can see */
const cols = computed(() => (branch.filterId !== null ? [branch.filterId] : [...myBranchIds.value]))
const shown = computed(() => {
  const s = q.value.trim().toLowerCase()
  return (books.value ?? []).filter((b) => !s || b.title.toLowerCase().includes(s))
})
const lowCount = computed(() => (books.value ?? []).filter((b) => cols.value.some((id) => b.stock[String(id)]?.low)).length)
const cell = (b: Book, id: number) => b.stock[String(id)]
const bookTitle = (id: number) => books.value?.find((b) => b.id === id)?.title ?? `#${id}`

async function loadBooks() {
  books.value = await booksApi.list(branch.filterId).catch(() => [])
}
async function loadTransfers() {
  if (canStock.value) transfers.value = await booksApi.transfers().catch(() => [])
}
async function loadReport() {
  report.value = null
  report.value = await booksApi.report({ period: period.value, branch_id: branch.filterId }).catch(() => null)
}
onMounted(() => {
  refs.load()
  loadBooks()
  loadTransfers()
})
watch(() => branch.filterId, () => {
  loadBooks()
  if (tab.value === 'report') loadReport()
})
watch([tab, period], () => tab.value === 'report' && loadReport(), { immediate: true })

function openBook(b: Book | null) {
  editing.value = b
  bookModal.value = true
}
function afterStock() {
  loadBooks()
  loadTransfers()
}
async function confirm(x: BookTransfer) {
  confirming.value = x.id
  try {
    await booksApi.confirm(x.id)
    toast.ok(t('books.confirmed', { n: x.qty }))
    afterStock()
  } finally {
    confirming.value = null
  }
}
const reportRows = computed(() => report.value?.books ?? [])
</script>

<template>
  <div class="ph">
    <div><h1>{{ t('books.title') }}</h1><p>{{ t('books.subtitle') }}</p></div>
    <span class="sp" />
    <UiButton v-if="auth.can('books.edit')" variant="primary" icon="plus" @click="openBook(null)">{{ t('books.new') }}</UiButton>
  </div>

  <div class="toolbar">
    <UiTabs v-model="tab" :items="tabs" :label="t('books.title')" />
    <UiPeriod v-if="tab === 'report'" v-model="period" />
  </div>

  <template v-if="tab === 'catalog'">
    <div v-if="lowCount" class="alert" role="status" style="margin-bottom: 14px"><span>{{ t('books.lowAlert', { n: lowCount }) }}</span></div>
    <UiCard flush>
      <div class="card-pad" style="padding-bottom: 0"><input v-model="q" class="inp" type="search" :placeholder="t('books.searchPh')" :aria-label="t('books.searchPh')" style="max-width: 320px" /></div>
      <div v-if="!books" class="card-pad"><UiSkeleton :lines="5" /></div>
      <UiEmptyState v-else-if="!shown.length" icon="book" :title="q ? t('common.nothingFound') : t('books.empty')" />
      <div v-else class="scroll-x">
        <table class="tbl" :style="{ minWidth: `${420 + cols.length * 96}px` }">
          <thead>
            <tr>
              <th>{{ t('books.book') }}</th>
              <th class="r">{{ t('books.salePrice') }}</th>
              <th v-if="canStock" class="r">{{ t('books.purchasePrice') }}</th>
              <th v-for="id in cols" :key="id" class="r">{{ refs.branchName(id) }}</th>
              <th v-if="canStock || auth.can('books.edit')" class="r"><span class="sr">{{ t('books.actions') }}</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="b in shown" :key="b.id">
              <td><b>{{ b.title }}</b><div v-if="b.level_id" style="margin-top: 2px"><LevelTag :id="b.level_id" /></div></td>
              <td class="r num">{{ money(b.sale_price, loc) }}</td>
              <td v-if="canStock" class="r num muted">{{ b.purchase_price != null ? money(b.purchase_price, loc) : '—' }}</td>
              <td v-for="id in cols" :key="id" class="r">
                <template v-if="cell(b, id)">
                  <b class="num" :class="{ redc: cell(b, id)?.low }">{{ cell(b, id)?.qty }}</b>
                  <div v-if="cell(b, id)?.low"><UiChip tone="red" small>{{ t('books.low', { n: cell(b, id)?.min_qty }) }}</UiChip></div>
                </template>
                <span v-else class="muted">0</span>
              </td>
              <td v-if="canStock || auth.can('books.edit')" class="r">
                <div class="row-acts nowrap">
                  <template v-if="canStock">
                    <UiButton size="sm" variant="ghost" icon="plus" :title="t('books.mode.receive')" :aria-label="`${t('books.mode.receive')}: ${b.title}`" @click="stock = { book: b, mode: 'receive' }" />
                    <UiButton size="sm" variant="ghost" icon="transfer" :title="t('books.mode.transfer')" :aria-label="`${t('books.mode.transfer')}: ${b.title}`" @click="stock = { book: b, mode: 'transfer' }" />
                    <UiButton size="sm" variant="ghost" icon="archive" :title="t('books.mode.writeoff')" :aria-label="`${t('books.mode.writeoff')}: ${b.title}`" @click="stock = { book: b, mode: 'writeoff' }" />
                  </template>
                  <UiButton v-if="auth.can('books.edit')" size="sm" variant="ghost" icon="edit" :title="t('common.edit')" :aria-label="`${t('common.edit')}: ${b.title}`" @click="openBook(b)" />
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </UiCard>
    <p class="muted" style="font-size: 12.5px; margin-top: 10px">{{ t('books.sellHint') }}</p>
  </template>

  <div v-else-if="tab === 'transfers'" class="grid fin-a">
    <UiCard :title="t('books.incoming')">
      <UiSkeleton v-if="!transfers" :lines="3" />
      <UiEmptyState v-else-if="!incoming.length" icon="transfer" :title="t('books.noIncoming')" />
      <div v-for="x in incoming" :key="x.id" class="list-row">
        <div class="grow"><b>{{ bookTitle(x.book_id) }} × {{ x.qty }}</b><span>{{ t('books.fromTo', { from: refs.branchName(x.from_branch_id), to: refs.branchName(x.to_branch_id) }) }} · {{ dmy(x.at, loc) }}</span></div>
        <UiButton size="sm" variant="navy" icon="ok" :loading="confirming === x.id" @click="confirm(x)">{{ t('books.confirm') }}</UiButton>
      </div>
    </UiCard>
    <UiCard :title="t('books.outgoing')">
      <UiSkeleton v-if="!transfers" :lines="3" />
      <UiEmptyState v-else-if="!outgoing.length" icon="transfer" :title="t('books.noOutgoing')" />
      <div v-for="x in outgoing" :key="x.id" class="list-row">
        <div class="grow"><b>{{ bookTitle(x.book_id) }} × {{ x.qty }}</b><span>{{ t('books.fromTo', { from: refs.branchName(x.from_branch_id), to: refs.branchName(x.to_branch_id) }) }} · {{ dmy(x.at, loc) }}</span></div>
        <UiChip tone="warn" small icon="clock">{{ t('books.inTransit') }}</UiChip>
      </div>
    </UiCard>
  </div>

  <template v-else>
    <div class="grid fin-k" style="grid-template-columns: repeat(auto-fit, minmax(180px, 1fr))">
      <div class="card kpi"><div class="k">{{ t('books.revenue') }}</div><div class="v num"><template v-if="report">{{ money(report.totals.revenue, loc) }}</template><UiSkeleton v-else width="60%" /></div><span class="muted" style="font-size: 12px">{{ periodLabel(period, loc) }}</span></div>
      <div class="card kpi"><div class="k">{{ t('books.profit') }}</div><div class="v num"><template v-if="report">{{ money(report.totals.profit, loc) }}</template><UiSkeleton v-else width="60%" /></div><span class="muted" style="font-size: 12px">{{ t('books.profitNote') }}</span></div>
      <div class="card kpi"><div class="k">{{ t('books.withoutBook') }}</div><div class="v num" :class="{ redc: (report?.students_without_book.length ?? 0) > 0 }"><template v-if="report">{{ report.students_without_book.length }}</template><UiSkeleton v-else width="40%" /></div><span class="muted" style="font-size: 12px">{{ t('books.withoutNote') }}</span></div>
    </div>
    <div class="grid fin-a">
      <UiCard :title="t('books.movements')" flush>
        <div v-if="!report" class="card-pad"><UiSkeleton :lines="4" /></div>
        <UiEmptyState v-else-if="!reportRows.length" icon="book" :title="t('books.noMovements')" />
        <div v-else class="scroll-x">
          <table class="tbl" style="min-width: 620px">
            <thead><tr><th>{{ t('books.book') }}</th><th class="r">{{ t('books.k.in') }}</th><th class="r">{{ t('books.k.sale') }}</th><th class="r">{{ t('books.k.writeoff') }}</th><th class="r">{{ t('books.k.transfer') }}</th><th class="r">{{ t('books.revenue') }}</th><th class="r">{{ t('books.profit') }}</th></tr></thead>
            <tbody class="num">
              <tr v-for="r in reportRows" :key="r.book_id">
                <td><b>{{ r.title }}</b></td>
                <td class="r">{{ r.in ?? 0 }}</td>
                <td class="r">{{ r.sale ?? 0 }}</td>
                <td class="r" :class="{ redc: (r.writeoff ?? 0) > 0 }">{{ r.writeoff ?? 0 }}</td>
                <td class="r">{{ (r.transfer_in ?? 0) }} / {{ r.transfer_out ?? 0 }}</td>
                <td class="r">{{ money(r.revenue ?? 0, loc) }}</td>
                <td class="r">{{ money(r.profit ?? 0, loc) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </UiCard>
      <UiCard :title="t('books.withoutBook')">
        <UiSkeleton v-if="!report" :lines="4" />
        <p v-else-if="!report.students_without_book.length" class="muted m0">{{ t('books.allHave') }}</p>
        <div v-else class="lr-list short-list">
          <RouterLink v-for="s in report.students_without_book.slice(0, 50)" :key="`${s.student_id}-${s.book}`" :to="`/students/${s.student_id}`" class="list-row">
            <div class="grow"><b>{{ s.full_name }}</b><span>{{ s.book }}</span></div>
          </RouterLink>
          <p v-if="report.students_without_book.length > 50" class="muted" style="font-size: 12.5px">{{ t('books.andMore', { n: report.students_without_book.length - 50 }) }}</p>
        </div>
      </UiCard>
    </div>
  </template>

  <BookModal v-model:open="bookModal" :book="editing" @saved="loadBooks" />
  <StockModal :open="!!stock" :book="stock?.book ?? null" :mode="stock?.mode ?? 'receive'" @update:open="(v) => !v && (stock = null)" @saved="afterStock" />
</template>
