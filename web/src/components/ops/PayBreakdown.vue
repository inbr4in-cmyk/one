<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { PayBreakdown } from '@/api/payroll'
import { money } from '@/utils/dates'
import type { Locale } from '@/i18n'

/** How the month's pay is made up: lessons by format at the rate, KPI extra, other accruals, total. */
defineProps<{ data: PayBreakdown }>()
const { t, te, locale } = useI18n()
const loc = computed(() => locale.value as Locale)
const title = (key: string, fallback: string) => (te(`nv.pay.k.${key}`) ? t(`nv.pay.k.${key}`) : te(`payroll.kind.${key}`) ? t(`payroll.kind.${key}`) : fallback)
</script>

<template>
  <div class="pb">
    <template v-if="data.lessons.length">
      <div class="pb-h">{{ t('nv.pay.rate') }}</div>
      <div v-for="r in data.lessons" :key="r.key" class="pb-r">
        <span>{{ title(r.key, r.title) }} <span class="muted num">× {{ r.count }}</span></span><b class="num">{{ money(r.amount, loc) }}</b>
      </div>
      <div class="pb-r sub">
        <span>{{ t('nv.pay.rateTotal', { n: data.lessons_count }) }}</span><b class="num">{{ money(data.lessons_total, loc) }}</b>
      </div>
    </template>
    <template v-if="data.kpi.amount || data.lessons.length">
      <div class="pb-h">KPI</div>
      <div class="pb-r">
        <span>{{ t('nv.pay.kpi') }} <span class="muted num">× {{ data.kpi.count }}</span></span><b class="num">{{ money(data.kpi.amount, loc) }}</b>
      </div>
    </template>
    <template v-if="data.other.length">
      <div class="pb-h">{{ t('nv.pay.other') }}</div>
      <div v-for="r in data.other" :key="r.key" class="pb-r">
        <span>{{ title(r.key, r.title) }} <span class="muted num">× {{ r.count }}</span></span><b class="num" :class="{ redc: r.amount < 0 }">{{ money(r.amount, loc) }}</b>
      </div>
    </template>
    <div class="pb-r total"><span>{{ t('nv.pay.total') }}</span><b class="num">{{ money(data.total, loc) }}</b></div>
  </div>
</template>

<style scoped>
.pb { display: grid; gap: 2px; border: 1px solid var(--line); border-radius: var(--r-sm); padding: 6px 14px 10px; }
.pb-h { margin-top: 8px; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }
.pb-r { display: flex; justify-content: space-between; gap: 12px; padding: 5px 0; }
.pb-r.sub { border-top: 1px dashed var(--line); color: var(--muted); }
.pb-r.sub b { color: var(--ink); }
.pb-r.total { margin-top: 8px; padding-top: 10px; border-top: 1px solid var(--line); font-weight: 700; font-size: 16px; }
</style>
