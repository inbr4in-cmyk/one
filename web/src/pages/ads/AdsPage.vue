<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiCard, UiEmptyState, UiInput, UiSkeleton } from '@/components/ui'
import { adsApi, type AdsReport } from '@/api/ads'
import { useToastStore } from '@/stores/toast'
import type { Locale } from '@/i18n'
import { dmy, hm, isoDate, schoolNow } from '@/utils/dates'

const { t, locale } = useI18n()
const loc = computed(() => locale.value as Locale)
const toast = useToastStore()
const now = schoolNow()
const f = reactive({ from: isoDate(new Date(now.getFullYear(), now.getMonth(), 1)), to: isoDate(now) })
const data = ref<AdsReport | null>(null)
const loading = ref(true)
const syncing = ref(false)

async function load() {
  loading.value = true
  try {
    data.value = await adsApi.report({ date_from: f.from, date_to: f.to })
  } catch {
    data.value = null
  } finally {
    loading.value = false
  }
}
watch(() => [f.from, f.to], load)
onMounted(load)

async function sync() {
  syncing.value = true
  try {
    await adsApi.sync()
    toast.ok(t('nv.ads.synced'))
    await load()
  } catch {
    /* toast */
  } finally {
    syncing.value = false
  }
}
const num = (n: number) => n.toLocaleString('ru-RU').replace(/,/g, ' ')
const cash = (n: number | null | undefined) => (n == null ? '—' : `${n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${data.value?.currency ?? ''}`.trim())
const maxSpend = computed(() => Math.max(1, ...(data.value?.days ?? []).map((d) => d.spend)))
</script>

<template>
  <div class="ph">
    <div><h1>{{ t('nav.ads') }}</h1><p class="muted m0">{{ t('nv.ads.sub') }}</p></div>
    <UiButton v-if="data?.configured" icon="clock" :loading="syncing" data-testid="ads-sync" @click="sync">{{ t('nv.ads.sync') }}</UiButton>
  </div>
  <div class="toolbar">
    <UiInput v-model="f.from" type="date" :max="f.to" class="tb-date" :aria-label="t('payments.from')" />
    <span class="muted">—</span>
    <UiInput v-model="f.to" type="date" :min="f.from" class="tb-date" :aria-label="t('payments.to')" />
    <span v-if="data?.synced_at" class="muted ad-when">{{ t('nv.ads.at', { d: `${dmy(data.synced_at, loc)} ${hm(data.synced_at, loc)}` }) }}</span>
  </div>
  <div v-if="loading && !data" class="card" style="padding: 18px"><UiSkeleton :lines="6" /></div>
  <UiEmptyState v-else-if="!data" icon="trend" :title="t('crm.noData')" />
  <UiEmptyState v-else-if="!data.configured && !data.days.length" icon="trend" :title="t('nv.ads.off')" :text="t('nv.ads.offText')" />
  <template v-else>
    <div class="grid kpis stagger" style="margin-bottom: 16px" data-testid="ads-kpis">
      <div class="card kpi"><div class="k">{{ t('nv.ads.spend') }}</div><div class="v num">{{ data.total.spend.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }} <small class="ad-cur">{{ data.currency }}</small></div></div>
      <div class="card kpi"><div class="k">{{ t('nv.ads.impressions') }}</div><div class="v num">{{ num(data.total.impressions) }}</div></div>
      <div class="card kpi"><div class="k">{{ t('nv.ads.clicks') }}</div><div class="v num">{{ num(data.total.clicks) }}</div><div class="muted ad-s">CTR {{ data.total.ctr }}% · {{ t('nv.ads.cpc') }} {{ cash(data.total.cpc) }}</div></div>
      <div class="card kpi"><div class="k">{{ t('nv.ads.leads') }}</div><div class="v num">{{ num(data.crm.leads) }}</div><div class="muted ad-s">{{ t('nv.ads.per') }} {{ cash(data.crm.cost_per_lead) }}</div></div>
      <div class="card kpi"><div class="k">{{ t('nv.ads.paid') }}</div><div class="v num">{{ num(data.crm.paid) }}</div><div class="muted ad-s">{{ t('nv.ads.per') }} {{ cash(data.crm.cost_per_paid) }}</div></div>
    </div>
    <UiCard :title="t('nv.ads.campaigns')" flush style="margin-bottom: 16px">
      <div class="scroll-x">
        <table class="ad-t">
          <thead><tr><th>{{ t('nv.ads.campaign') }}</th><th class="r">{{ t('nv.ads.spend') }}</th><th class="r">{{ t('nv.ads.impressions') }}</th><th class="r">{{ t('nv.ads.reach') }}</th><th class="r">{{ t('nv.ads.clicks') }}</th><th class="r">CTR</th><th class="r">{{ t('nv.ads.cpc') }}</th><th class="r">{{ t('nv.ads.results') }}</th></tr></thead>
          <tbody class="num">
            <tr v-for="c in data.campaigns" :key="c.id"><td><b>{{ c.name || c.id }}</b></td><td class="r">{{ cash(c.spend) }}</td><td class="r">{{ num(c.impressions) }}</td><td class="r">{{ num(c.reach) }}</td><td class="r">{{ num(c.clicks) }}</td><td class="r">{{ c.ctr }}%</td><td class="r">{{ cash(c.cpc) }}</td><td class="r">{{ num(c.results) }}</td></tr>
            <tr v-if="!data.campaigns.length"><td colspan="8" class="muted">{{ t('nv.ads.none') }}</td></tr>
          </tbody>
        </table>
      </div>
    </UiCard>
    <UiCard v-if="data.days.length" :title="t('nv.ads.byDay')">
      <div v-for="d in data.days" :key="d.day" class="src-row ad-day">
        <span class="nm">{{ dmy(d.day, loc) }}</span>
        <span class="tr"><i :style="{ width: `${(d.spend / maxSpend) * 100}%` }" /></span>
        <span class="vv">{{ cash(d.spend) }}</span>
        <span class="vv">{{ num(d.clicks) }}</span>
      </div>
    </UiCard>
  </template>
</template>

<style scoped>
.ad-cur { font-size: 14px; font-weight: 600; color: var(--muted) }
.ad-when { font-size: 12px; margin-left: 6px }
.ad-s { font-size: 12px; margin-top: 4px }
.ad-t { min-width: 820px }
.ad-t th { white-space: nowrap }
.ad-day { grid-template-columns: 96px minmax(0, 1fr) 120px 64px }
</style>
