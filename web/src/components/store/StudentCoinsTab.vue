<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiCard, UiEmptyState, UiIcon, UiSkeleton } from '@/components/ui'
import CoinsModal from './CoinsModal.vue'
import { coinsApi, shopApi, type CoinEntry, type ShopOrder } from '@/api/store'
import { useAuthStore } from '@/stores/auth'
import { dmy } from '@/utils/dates'
import { num } from '@/utils/period'
import type { Locale } from '@/i18n'

/** Coins tab on the student card: balance, history, shop orders, award / write off. */
const props = defineProps<{ student: { id: number; full_name: string } }>()
const { t, te, locale } = useI18n()
const auth = useAuthStore()
const loc = computed(() => locale.value as Locale)
const data = ref<{ balance: number; items: CoinEntry[] } | null>(null)
const orders = ref<ShopOrder[]>([])
const modal = ref<'award' | 'writeoff' | null>(null)

async function load() {
  data.value = await coinsApi.ofStudent(props.student.id).catch(() => ({ balance: 0, items: [] }))
  if (auth.can('shop.view')) orders.value = await shopApi.orders({ student_id: props.student.id }).catch(() => [])
}
onMounted(load)
const kind = (k: string) => (te(`coins.kind.${k}`) ? t(`coins.kind.${k}`) : k)
</script>

<template>
  <div>
    <div class="grid fin-a">
      <UiCard :title="t('coins.history')">
        <template #actions>
          <UiButton v-if="auth.can('coins.writeoff')" size="sm" variant="ghost" @click="modal = 'writeoff'">{{ t('coins.writeoff') }}</UiButton>
          <UiButton v-if="auth.can('coins.award')" size="sm" variant="navy" icon="coin" @click="modal = 'award'">{{ t('coins.award') }}</UiButton>
        </template>
        <UiSkeleton v-if="!data" :lines="4" />
        <UiEmptyState v-else-if="!data.items.length" icon="coin" :title="t('coins.noHistory')" />
        <div v-else class="short-list">
          <div v-for="(e, i) in data.items" :key="i" class="list-row">
            <div class="grow"><b>{{ e.reason || kind(e.kind) }}</b><span>{{ kind(e.kind) }} · {{ dmy(e.at, loc) }}</span></div>
            <b class="num" :class="e.delta > 0 ? 'okc' : 'redc'">{{ e.delta > 0 ? '+' : '' }}{{ num(e.delta, loc) }}</b>
          </div>
        </div>
      </UiCard>
      <div class="grid" style="align-content: start; grid-template-columns: minmax(0, 1fr)">
        <UiCard :title="t('coins.balance')">
          <div class="coin-big num"><UiIcon name="coin" :size="24" /> <template v-if="data">{{ num(data.balance, loc) }}</template><UiSkeleton v-else width="80px" /></div>
        </UiCard>
        <UiCard v-if="auth.can('shop.view')" :title="t('shop.tab.orders')">
          <p v-if="!orders.length" class="muted m0">{{ t('shop.noOrders') }}</p>
          <div v-for="o in orders.slice(0, 8)" :key="o.id" class="list-row">
            <div class="grow"><b>{{ o.item }}</b><span>{{ dmy(o.created_at, loc) }} · {{ o.coins }} {{ t('coins.unit') }}</span></div>
            <span class="muted" style="font-size: 12.5px">{{ t(`shop.status.${o.status}`) }}</span>
          </div>
        </UiCard>
      </div>
    </div>
    <CoinsModal :open="!!modal" :student="student" :mode="modal ?? 'award'" @update:open="(v) => !v && (modal = null)" @done="load" />
  </div>
</template>
