<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiCard, UiEmptyState, UiIcon, UiSkeleton } from '@/components/ui'
import { portalApi, type PortalPayments } from '@/api/portal'
import { usePortalStore } from '@/stores/portal'
import { dmy, money } from '@/utils/dates'
import type { Locale } from '@/i18n'

/** Balance and payment history. Stays open while access is blocked: this is how a parent sees what to pay. */
const { t, te, locale } = useI18n()
const portal = usePortalStore()
const loc = computed(() => locale.value as Locale)
const data = ref<PortalPayments | null>(null)

watch(() => portal.child?.id, async (id) => {
  data.value = null
  if (id) data.value = await portalApi.payments(id).catch(() => null)
}, { immediate: true })
const cat = (c: string) => (te(`fin.revCat.${c}`) ? t(`fin.revCat.${c}`) : c)
const method = (m: string) => (te(`payments.method.${m}`) ? t(`payments.method.${m}`) : m)
</script>

<template>
  <div class="ph"><div><h1>{{ t('portal.nav.payments') }}</h1><p>{{ portal.child?.full_name }}</p></div></div>
  <div v-if="!data" class="card card-pad"><UiSkeleton :lines="5" /></div>
  <template v-else>
    <div class="grid fin-k" style="grid-template-columns: repeat(2, minmax(0, 1fr))">
      <div class="card kpi"><div class="k">{{ t('portal.lessonsLeft') }}</div><div class="v num" :class="{ redc: data.lessons_left <= 0 }">{{ data.lessons_left }}</div><span v-if="data.lesson_price" class="muted" style="font-size: 12px">{{ t('portal.pricePer', { sum: money(data.lesson_price, loc) }) }}</span></div>
      <div class="card kpi"><div class="k">{{ t('portal.balance') }}</div><div class="v num">{{ money(data.money_balance, loc) }}</div><span v-if="data.debt_lessons" class="redc" style="font-size: 12px">{{ t('portal.debtLessons', { n: data.debt_lessons }) }}</span></div>
    </div>
    <div v-if="data.debt_lessons || data.blocked" class="alert red">
      <UiIcon name="debt" :size="18" class="ico" />
      <div class="grow">
        <b>{{ data.blocked ? t('portal.blockedTitle') : t('portal.debtTitle') }}</b>
        <span>{{ t('portal.payHow', { sum: data.lesson_price ? money(data.lesson_price * data.debt_lessons, loc) : '—' }) }}</span>
      </div>
    </div>
    <UiCard :title="t('portal.history')">
      <UiEmptyState v-if="!data.items.length" icon="wallet" :title="t('portal.noPayments')" />
      <div v-for="p in data.items" :key="p.id" class="list-row">
        <div class="grow">
          <b class="num">{{ money(p.amount, loc) }}</b>
          <span>{{ dmy(p.paid_at, loc) }} · {{ cat(p.category) }} · {{ method(p.method) }}<template v-if="p.lessons"> · {{ t('students.nLessons', { n: p.lessons }) }}</template></span>
          <span v-if="p.note" style="display: block">{{ p.note }}</span>
        </div>
        <span v-if="p.refunded" class="redc num" style="font-size: 12.5px">{{ t('payments.refunded', { sum: money(p.refunded, loc) }) }}</span>
      </div>
    </UiCard>
  </template>
</template>
