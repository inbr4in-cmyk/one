<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiCard, UiEmptyState, UiInput, UiSkeleton } from '@/components/ui'
import { crmApi, type Analytics, type Funnel } from '@/api/crm'
import { useBranchStore } from '@/stores/branch'
import { useRefsStore } from '@/stores/refs'
import { isoDate } from '@/utils/dates'

const { t, te } = useI18n()
const branch = useBranchStore()
const refs = useRefsStore()
const now = new Date()
const f = reactive({ from: isoDate(new Date(now.getFullYear(), now.getMonth(), 1)), to: isoDate(now) })
const data = ref<Analytics | null>(null)
const loading = ref(true)

async function load() {
  loading.value = true
  try {
    data.value = await crmApi.analytics({ date_from: f.from, date_to: f.to, branch_id: branch.filterId })
  } catch {
    data.value = null
  } finally {
    loading.value = false
  }
}
watch(() => [f.from, f.to, branch.filterId], load)
onMounted(load)

const STEPS = ['new', 'contacted', 'trial_booked', 'trial_done', 'paid'] as const
const funnel = computed(() => {
  const tot = data.value?.total
  if (!tot) return []
  const max = Math.max(1, tot.new)
  return STEPS.map((k, i) => ({
    k, n: tot[k], w: (tot[k] / max) * 100,
    conv: i ? Math.round((tot[k] / Math.max(1, tot[STEPS[i - 1]!])) * 100) : null,
  }))
})
const rows = (rec: Record<string, Funnel> | undefined, label: (k: string) => string) =>
  Object.entries(rec ?? {}).map(([k, v]) => ({ k, name: label(k), ...v })).sort((a, b) => b.new - a.new)
const bySource = computed(() => rows(data.value?.by_source, (k) => (te(`crm.source.${k}`) ? t(`crm.source.${k}`) : k)))
const byOwner = computed(() => (data.value?.by_owner ?? []).map((r) => ({ ...r, k: String(r.user_id ?? 'none'), name: r.name ?? t('crm.unassigned') })).sort((a, b) => b.new - a.new))
const byBranch = computed(() => rows(data.value?.by_branch, (k) => (/^\d+$/.test(k) ? refs.branchName(Number(k)) : k)))
const lost = computed(() => {
  const e = Object.entries(data.value?.lost_reasons ?? {}).sort((a, b) => b[1] - a[1])
  const max = Math.max(1, ...e.map(([, n]) => n))
  return e.map(([k, n]) => ({ k, n, w: (n / max) * 100 }))
})
const pct = (n: number) => `${Math.round(n)}%`
</script>

<template>
  <div class="toolbar">
    <UiInput v-model="f.from" type="date" :max="f.to" class="tb-date" :aria-label="t('payments.from')" />
    <span class="muted">—</span>
    <UiInput v-model="f.to" type="date" :min="f.from" class="tb-date" :aria-label="t('payments.to')" />
  </div>
  <div v-if="loading" class="grid dash-a"><div v-for="i in 2" :key="i" class="card" style="padding: 18px"><UiSkeleton :lines="5" /></div></div>
  <UiEmptyState v-else-if="!data" icon="funnel" :title="t('crm.noData')" />
  <template v-else>
    <div class="grid kpis stagger" style="margin-bottom: 16px">
      <div class="card kpi"><div class="k">{{ t('crm.a.leads') }}</div><div class="v num">{{ data.total.new }}</div></div>
      <div class="card kpi"><div class="k">{{ t('crm.a.trials') }}</div><div class="v num">{{ data.total.trial_done }}</div></div>
      <div class="card kpi"><div class="k">{{ t('crm.a.paid') }}</div><div class="v num">{{ data.total.paid }}</div></div>
      <div class="card kpi"><div class="k">{{ t('crm.a.conversion') }}</div><div class="v num">{{ pct(data.total.conversion) }}</div></div>
      <div class="card kpi"><div class="k">{{ t('crm.a.lost') }}</div><div class="v num">{{ data.total.lost }}</div></div>
    </div>
    <div class="grid dash-a">
      <UiCard :title="t('crm.a.funnel')" icon="funnel">
        <div v-for="s in funnel" :key="s.k" class="src-row">
          <span class="nm">{{ t(`crm.stage.${s.k}`) }}</span>
          <span class="tr"><i :style="{ width: `${s.w}%` }" /></span>
          <span class="vv">{{ s.n }}<span v-if="s.conv !== null">{{ s.conv }}%</span></span>
        </div>
      </UiCard>
      <UiCard :title="t('crm.a.lostReasons')" icon="refusal">
        <div v-for="r in lost" :key="r.k" class="src-row">
          <span class="nm">{{ r.k }}</span>
          <span class="tr"><i :style="{ width: `${r.w}%`, background: 'var(--muted)' }" /></span>
          <span class="vv">{{ r.n }}</span>
        </div>
        <p v-if="!lost.length" class="muted m0">{{ t('crm.noData') }}</p>
      </UiCard>
    </div>
    <div class="grid an-tables">
      <UiCard v-for="tbl in [{ title: t('crm.a.bySource'), rows: bySource }, { title: t('crm.a.byOwner'), rows: byOwner }, { title: t('crm.a.byBranch'), rows: byBranch }]" :key="tbl.title" :title="tbl.title" flush>
        <div class="scroll-x">
          <table>
            <thead><tr><th /><th class="r">{{ t('crm.a.leads') }}</th><th class="r">{{ t('crm.a.trials') }}</th><th class="r">{{ t('crm.a.paid') }}</th><th class="r">%</th></tr></thead>
            <tbody class="num">
              <tr v-for="r in tbl.rows" :key="r.k"><td><b>{{ r.name }}</b></td><td class="r">{{ r.new }}</td><td class="r">{{ r.trial_done }}</td><td class="r">{{ r.paid }}</td><td class="r">{{ pct(r.conversion) }}</td></tr>
              <tr v-if="!tbl.rows.length"><td colspan="5" class="muted">{{ t('crm.noData') }}</td></tr>
            </tbody>
          </table>
        </div>
      </UiCard>
    </div>
  </template>
</template>
