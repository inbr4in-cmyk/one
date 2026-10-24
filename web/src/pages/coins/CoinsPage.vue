<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiAvatar, UiButton, UiCard, UiChip, UiEmptyState, UiIcon, UiPeriod, UiPrompt, UiSegmented, UiSkeleton, UiTabs } from '@/components/ui'
import CoinsModal from '@/components/store/CoinsModal.vue'
import ShopItemModal from '@/components/store/ShopItemModal.vue'
import { coinsApi, shopApi, type LeaderRow, type OrderStatus, type ShopItem, type ShopOrder } from '@/api/store'
import { useAuthStore } from '@/stores/auth'
import { useBranchStore } from '@/stores/branch'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import { relativeTime } from '@/utils/format'
import { num, periodOf } from '@/utils/period'
import { iconOr } from '@/utils/icons'
import type { Locale } from '@/i18n'

type Tab = 'orders' | 'top' | 'items'
const { t, locale } = useI18n()
const auth = useAuthStore()
const branch = useBranchStore()
const refs = useRefsStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)

const tabs = computed(() => [
  ...(auth.can('shop.view') ? [{ value: 'orders' as const, label: t('shop.tab.orders'), count: openCount.value || undefined }] : []),
  ...(auth.can('coins.view') ? [{ value: 'top' as const, label: t('coins.tab.top') }] : []),
  ...(auth.can('shop.view') ? [{ value: 'items' as const, label: t('shop.tab.items') }] : []),
])
const tab = ref<Tab>(auth.can('shop.view') ? 'orders' : 'top')
const status = ref<OrderStatus | 'open' | ''>('open')
const orders = ref<ShopOrder[] | null>(null)
const items = ref<ShopItem[] | null>(null)
const top = ref<LeaderRow[] | null>(null)
const coinsModal = ref(false)
const itemModal = ref(false)
const editing = ref<ShopItem | null>(null)
const cancelling = ref<ShopOrder | null>(null)
const acting = ref<number | null>(null)
const archiving = ref<ShopItem | null>(null)
/** Leaderboard: a calendar month or all time */
const topRange = ref<'month' | 'all'>('month')
const topPeriod = ref(periodOf())
const rangeOptions = computed(() => [{ value: 'month' as const, label: t('coins.range.month') }, { value: 'all' as const, label: t('coins.range.all') }])
const canEditItem = (i: ShopItem) => auth.can('shop.edit') && (i.branch_id !== null || auth.can('shop.edit', 'network'))

const statusOptions = computed(() => (['open', 'issued', 'cancelled', ''] as const).map((s) => ({ value: s, label: t(`shop.filter.${s || 'all'}`) })))
const shownOrders = computed(() => {
  const list = (orders.value ?? []).filter((o) => branch.filterId === null || o.branch_id === branch.filterId)
  return status.value === 'open' ? list.filter((o) => o.status === 'placed' || o.status === 'ready') : status.value ? list.filter((o) => o.status === status.value) : list
})
const openCount = computed(() => (orders.value ?? []).filter((o) => (o.status === 'placed' || o.status === 'ready') && (branch.filterId === null || o.branch_id === branch.filterId)).length)
const ORDER_TONE: Record<OrderStatus, 'info' | 'ok' | 'warn' | undefined> = { placed: 'warn', ready: 'info', issued: 'ok', cancelled: undefined }

async function loadOrders() {
  if (auth.can('shop.view')) orders.value = await shopApi.orders().catch(() => [])
}
async function loadItems() {
  if (auth.can('shop.view')) items.value = await shopApi.items(branch.filterId).catch(() => [])
}
async function loadTop() {
  if (!auth.can('coins.view')) return
  top.value = null
  top.value = await coinsApi.top({ branch_id: branch.filterId, period: topRange.value === 'month' ? topPeriod.value : null, limit: 50 }).catch(() => [])
}
onMounted(() => {
  refs.load()
  loadOrders()
})
watch([tab, () => branch.filterId], () => {
  if (tab.value === 'items') loadItems()
  if (tab.value === 'top') loadTop()
}, { immediate: true })
watch([topRange, topPeriod], loadTop)

async function setStatus(o: ShopOrder, s: 'ready' | 'issued' | 'cancelled') {
  acting.value = o.id
  try {
    await shopApi.setStatus(o.id, s)
    toast.ok(t(`shop.st.${s}`))
    cancelling.value = null
    loadOrders()
    if (s === 'cancelled') loadItems()
  } finally {
    acting.value = null
  }
}
async function archiveItem() {
  const i = archiving.value
  if (!i) return
  acting.value = i.id
  try {
    await shopApi.archive(i.id)
    toast.ok(t('shop.archived'))
    archiving.value = null
    loadItems()
  } finally {
    acting.value = null
  }
}
function openItem(i: ShopItem | null) {
  editing.value = i
  itemModal.value = true
}
</script>

<template>
  <div class="ph">
    <div><h1>{{ t('coins.title') }}</h1><p>{{ t('coins.subtitle') }}</p></div>
    <span class="sp" />
    <UiButton v-if="auth.can('shop.edit') && tab === 'items'" icon="plus" @click="openItem(null)">{{ t('shop.new') }}</UiButton>
    <UiButton v-if="auth.can('coins.award') || auth.can('coins.writeoff')" variant="primary" icon="coin" @click="coinsModal = true">{{ auth.can('coins.award') ? t('coins.award') : t('coins.writeoff') }}</UiButton>
  </div>

  <div class="toolbar">
    <UiTabs v-model="tab" :items="tabs" :label="t('coins.title')" />
    <UiSegmented v-if="tab === 'orders'" v-model="status" :options="statusOptions" :label="t('shop.statusLabel')" size="sm" class="wrap" />
    <template v-if="tab === 'top'">
      <UiSegmented v-model="topRange" :options="rangeOptions" :label="t('coins.range.label')" size="sm" />
      <UiPeriod v-if="topRange === 'month'" v-model="topPeriod" />
    </template>
  </div>

  <UiCard v-if="tab === 'orders'" flush>
    <div v-if="!orders" class="card-pad"><UiSkeleton :lines="4" /></div>
    <UiEmptyState v-else-if="!shownOrders.length" icon="shop" :title="status === 'open' ? t('shop.noOpen') : t('shop.noOrders')" />
    <div v-else class="card-b">
      <div v-for="o in shownOrders" :key="o.id" class="list-row order-row">
        <UiAvatar :name="o.student" size="sm" />
        <div class="grow">
          <b><RouterLink v-if="auth.can('students.view')" :to="`/students/${o.student_id}`" class="rowlink">{{ o.student }}</RouterLink><template v-else>{{ o.student }}</template></b>
          <span>{{ o.item }} · <span class="num">{{ o.coins }}</span> {{ t('coins.unit') }} · {{ refs.branchName(o.branch_id) }} · {{ relativeTime(o.created_at, loc) }}</span>
        </div>
        <UiChip :tone="ORDER_TONE[o.status]" small>{{ t(`shop.status.${o.status}`) }}</UiChip>
        <div v-if="auth.can('shop.issue') && (o.status === 'placed' || o.status === 'ready')" class="row-acts">
          <UiButton v-if="o.status === 'placed'" size="sm" :loading="acting === o.id" @click="setStatus(o, 'ready')">{{ t('shop.do.ready') }}</UiButton>
          <UiButton size="sm" variant="navy" icon="ok" :loading="acting === o.id" @click="setStatus(o, 'issued')">{{ t('shop.do.issued') }}</UiButton>
          <UiButton size="sm" variant="ghost" icon="x" :aria-label="t('shop.do.cancelled')" :title="t('shop.do.cancelled')" @click="cancelling = o" />
        </div>
      </div>
    </div>
  </UiCard>

  <UiCard v-else-if="tab === 'top'" :title="t('coins.leaderboard')">
    <UiSkeleton v-if="!top" :lines="6" />
    <UiEmptyState v-else-if="!top.length" icon="trophy" :title="t('coins.noTop')" />
    <ol v-else class="leader">
      <li v-for="(r, i) in top" :key="r.student_id ?? i" :class="{ podium: i < 3 }">
        <span class="rank-n" :class="{ g: i < 3 }">{{ i + 1 }}</span>
        <UiAvatar :name="r.name" size="sm" />
        <div class="grow">
          <b><RouterLink v-if="r.student_id && auth.can('students.view')" :to="`/students/${r.student_id}`" class="rowlink">{{ r.name }}</RouterLink><template v-else>{{ r.name }}</template></b>
          <span>{{ refs.branchName(r.branch_id) }}</span>
        </div>
        <b class="num coin-v"><UiIcon name="coin" :size="14" /> {{ num(r.coins, loc) }}</b>
      </li>
    </ol>
    <p class="muted m0" style="font-size: 12.5px; margin-top: 12px">{{ topRange === 'month' ? t('coins.topNoteMonth') : t('coins.topNote') }}</p>
  </UiCard>

  <template v-else>
    <div v-if="!items" class="card card-pad"><UiSkeleton :lines="4" /></div>
    <UiEmptyState v-else-if="!items.length" icon="shop" :title="t('shop.noItems')" />
    <div v-else class="shop-grid">
      <div v-for="i in items" :key="i.id" class="card shop-item">
        <div class="shop-ico"><UiIcon :name="iconOr(i.icon, 'gift')" :size="24" /></div>
        <b>{{ i.name }}</b>
        <span class="num coin-v"><UiIcon name="coin" :size="14" /> {{ num(i.price_coins, loc) }}</span>
        <span class="muted" style="font-size: 12px">
          <template v-if="i.stock">{{ t('shop.inStock', { n: i.stock }) }}</template><span v-else class="redc">{{ t('shop.outOfStock') }}</span>
          · {{ i.branch_id ? refs.branchName(i.branch_id) : t('shop.allBranches') }}
          <template v-if="i.cost != null"> · {{ t('shop.costN', { n: num(i.cost, loc) }) }}</template>
        </span>
        <div v-if="canEditItem(i)" class="row-acts nowrap">
          <UiButton size="sm" variant="ghost" icon="edit" @click="openItem(i)">{{ t('common.edit') }}</UiButton>
          <UiButton size="sm" variant="ghost" icon="archive" :aria-label="t('shop.archive')" :title="t('shop.archive')" @click="archiving = i" />
        </div>
      </div>
    </div>
  </template>

  <CoinsModal v-model:open="coinsModal" @done="tab === 'top' && loadTop()" />
  <ShopItemModal v-model:open="itemModal" :item="editing" @saved="loadItems" />
  <UiPrompt :open="!!archiving" :title="t('shop.archiveTitle')" :text="archiving ? t('shop.archiveText', { item: archiving.name }) : ''" :confirm-label="t('shop.archive')" danger :busy="acting === archiving?.id" @update:open="(v) => !v && (archiving = null)" @confirm="archiveItem" />
  <UiPrompt :open="!!cancelling" :title="t('shop.cancelTitle')" :text="cancelling ? t('shop.cancelText', { item: cancelling.item, name: cancelling.student, n: cancelling.coins }) : ''" :confirm-label="t('shop.do.cancelled')" danger :busy="acting === cancelling?.id" @update:open="(v) => !v && (cancelling = null)" @confirm="cancelling && setStatus(cancelling, 'cancelled')" />
</template>
