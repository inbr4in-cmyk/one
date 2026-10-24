<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiAvatar, UiButton, UiCard, UiChip, UiEmptyState, UiIcon, UiPrompt, UiSegmented, UiSkeleton, UiTabs } from '@/components/ui'
import { coinsApi, shopApi, type LeaderRow, type ShopItem, type ShopOrder } from '@/api/store'
import { usePortalStore } from '@/stores/portal'
import { useToastStore } from '@/stores/toast'
import { dmy } from '@/utils/dates'
import { apiErr } from '@/utils/err'
import { num } from '@/utils/period'
import { iconOr } from '@/utils/icons'
import type { Locale } from '@/i18n'

/** Coins: balance, the shop (order, cancel a new order), and the group / branch leaderboard. */
const { t, locale } = useI18n()
const portal = usePortalStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)
const tab = ref<'shop' | 'orders' | 'top'>('shop')
const tabs = computed(() => [
  { value: 'shop' as const, label: t('portal.shop') },
  { value: 'orders' as const, label: t('portal.orders'), count: orders.value?.filter((o) => o.status === 'placed' || o.status === 'ready').length || undefined },
  { value: 'top' as const, label: t('portal.top') },
])
const items = ref<ShopItem[] | null>(null)
const orders = ref<ShopOrder[] | null>(null)
const top = ref<LeaderRow[] | null>(null)
const scope = ref<'group' | 'branch'>('group')
const balance = ref(0)
const buying = ref<ShopItem | null>(null)
const cancelling = ref<ShopOrder | null>(null)
const busy = ref(false)
const child = computed(() => portal.child)
const group = computed(() => child.value?.groups[0] ?? null)
const scopes = computed(() => [...(group.value ? [{ value: 'group' as const, label: t('portal.myGroup') }] : []), { value: 'branch' as const, label: t('portal.myBranch') }])

async function loadOrders() {
  if (child.value) orders.value = await shopApi.orders({ student_id: child.value.id }).catch(() => [])
}
async function loadTop() {
  const c = child.value
  if (!c) return
  top.value = null
  const useGroup = scope.value === 'group' && group.value
  top.value = await coinsApi.top(useGroup ? { group_id: group.value!.id, limit: 20 } : { branch_id: c.branch.id, limit: 20 }).catch(() => [])
}
watch(() => child.value?.id, async () => {
  const c = child.value
  items.value = orders.value = top.value = null
  if (!c) return
  balance.value = c.coins
  if (!group.value) scope.value = 'branch'
  const [i] = await Promise.all([shopApi.items(c.branch.id).catch(() => []), loadOrders()])
  items.value = i
  if (tab.value === 'top') loadTop()
}, { immediate: true })
watch([tab, scope], () => tab.value === 'top' && loadTop())

async function buy() {
  const it = buying.value
  const c = child.value
  if (!it || !c) return
  busy.value = true
  try {
    const r = await shopApi.order(c.id, it.id)
    balance.value = r.balance
    c.coins = r.balance
    it.stock -= 1
    buying.value = null
    toast.ok(t('portal.ordered', { item: it.name }))
    loadOrders()
  } catch (e) {
    toast.error(apiErr(e) ?? t('errors.generic'))
  } finally {
    busy.value = false
  }
}
async function cancel() {
  const o = cancelling.value
  if (!o) return
  busy.value = true
  try {
    await shopApi.setStatus(o.id, 'cancelled')
    balance.value += o.coins
    if (child.value) child.value.coins = balance.value
    cancelling.value = null
    toast.ok(t('shop.st.cancelled'))
    loadOrders()
    items.value = await shopApi.items(child.value!.branch.id).catch(() => items.value)
  } catch (e) {
    toast.error(apiErr(e) ?? t('errors.generic'))
  } finally {
    busy.value = false
  }
}
const TONE = { placed: 'warn', ready: 'info', issued: 'ok', cancelled: undefined } as const
</script>

<template>
  <div class="ph"><div><h1>{{ t('portal.nav.coins') }}</h1><p>{{ t('portal.coinsSub') }}</p></div></div>
  <div class="p-coins"><UiIcon name="coin" :size="24" class="warnc" /><div><b class="num">{{ num(balance, loc) }}</b><div><span>{{ t('portal.coinsBalance') }}</span></div></div></div>
  <div class="toolbar"><UiTabs v-model="tab" :items="tabs" :label="t('portal.nav.coins')" /></div>

  <template v-if="tab === 'shop'">
    <div v-if="!items" class="card card-pad"><UiSkeleton :lines="4" /></div>
    <UiEmptyState v-else-if="!items.length" icon="shop" :title="t('shop.noItems')" />
    <div v-else class="p-shop">
      <div v-for="i in items" :key="i.id" class="card shop-item">
        <div class="shop-ico"><UiIcon :name="iconOr(i.icon, 'gift')" :size="24" /></div>
        <b>{{ i.name }}</b>
        <span class="num coin-v"><UiIcon name="coin" :size="14" /> {{ num(i.price_coins, loc) }}</span>
        <span v-if="!i.stock" class="redc" style="font-size: 12px">{{ t('shop.outOfStock') }}</span>
        <span v-else-if="balance < i.price_coins" class="muted" style="font-size: 12px">{{ t('portal.needMore', { n: num(i.price_coins - balance, loc) }) }}</span>
        <UiButton size="sm" variant="navy" :disabled="!i.stock || balance < i.price_coins || portal.blocked" @click="buying = i">{{ t('portal.buy') }}</UiButton>
      </div>
    </div>
  </template>

  <UiCard v-else-if="tab === 'orders'">
    <UiSkeleton v-if="!orders" :lines="3" />
    <UiEmptyState v-else-if="!orders.length" icon="bag" :title="t('portal.noOrders')" />
    <div v-for="o in orders ?? []" :key="o.id" class="list-row">
      <div class="grow"><b>{{ o.item }}</b><span>{{ dmy(o.created_at, loc) }} · {{ o.coins }} {{ t('coins.unit') }}<template v-if="o.status === 'ready'"> · {{ t('portal.pickUp') }}</template></span></div>
      <UiChip :tone="TONE[o.status]" small>{{ t(`shop.status.${o.status}`) }}</UiChip>
      <UiButton v-if="o.status === 'placed'" size="sm" variant="ghost" icon="x" :aria-label="t('shop.do.cancelled')" :title="t('shop.do.cancelled')" @click="cancelling = o" />
    </div>
  </UiCard>

  <UiCard v-else :title="t('coins.leaderboard')">
    <template v-if="scopes.length > 1" #actions><UiSegmented v-model="scope" :options="scopes" :label="t('portal.top')" size="sm" /></template>
    <UiSkeleton v-if="!top" :lines="6" />
    <UiEmptyState v-else-if="!top.length" icon="trophy" :title="t('coins.noTop')" />
    <ol v-else class="leader">
      <li v-for="(r, i) in top" :key="i">
        <span class="rank-n" :class="{ g: i < 3 }">{{ i + 1 }}</span>
        <UiAvatar :name="r.name" size="sm" />
        <div class="grow"><b>{{ r.name }}</b></div>
        <b class="num coin-v"><UiIcon name="coin" :size="14" /> {{ num(r.coins, loc) }}</b>
      </li>
    </ol>
  </UiCard>

  <UiPrompt :open="!!buying" :title="t('portal.buyTitle')" :text="buying ? t('portal.buyText', { item: buying.name, n: buying.price_coins }) : ''" :confirm-label="t('portal.buy')" :busy="busy" @update:open="(v) => !v && (buying = null)" @confirm="buy" />
  <UiPrompt :open="!!cancelling" :title="t('shop.cancelTitle')" :text="cancelling ? t('portal.cancelText', { item: cancelling.item, n: cancelling.coins }) : ''" :confirm-label="t('shop.do.cancelled')" danger :busy="busy" @update:open="(v) => !v && (cancelling = null)" @confirm="cancel" />
</template>
