<script setup lang="ts">
import { useSourceLabel } from '@/composables/useSourceLabel'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiCard, UiEmptyState, UiInput, UiSelect, UiSkeleton } from '@/components/ui'
import { tone } from '@/utils/levels'
import { crmApi, type Analytics, type Funnel } from '@/api/crm'
import { useBranchStore } from '@/stores/branch'
import { useRefsStore } from '@/stores/refs'
import { useSourcesStore } from '@/stores/sources'
import { isoDate, schoolNow } from '@/utils/dates'

const { t } = useI18n()
const branch = useBranchStore()
const refs = useRefsStore()
const now = schoolNow()
const f = reactive({ from: isoDate(new Date(now.getFullYear(), now.getMonth(), 1)), to: isoDate(now) })
const data = ref<Analytics | null>(null)
const loading = ref(true)
const manager = ref(0)
const source = ref('')
const sources = useSourcesStore()

async function load() {
  loading.value = true
  try {
    data.value = await crmApi.analytics({ date_from: f.from, date_to: f.to, branch_id: branch.filterId, manager_id: manager.value || null, source: source.value || null })
  } catch {
    data.value = null
  } finally {
    loading.value = false
  }
}
watch(() => [f.from, f.to, branch.filterId, manager.value, source.value], load)
onMounted(load)

const rows = (rec: Record<string, Funnel> | undefined, label: (k: string) => string) =>
  Object.entries(rec ?? {}).map(([k, v]) => ({ k, name: label(k), ...v })).sort((a, b) => b.new - a.new)
const srcLabel = useSourceLabel()
const bySource = computed(() => rows(data.value?.by_source, (k) => srcLabel(k)))
const byBranch = computed(() => rows(data.value?.by_branch, (k) => (/^\d+$/.test(k) ? refs.branchName(Number(k)) : t('nv.noBranch'))))
const managerOptions = computed(() => [{ value: 0, label: t('crm.allOwners') }, ...(data.value?.managers ?? []).filter((m) => m.user_id).map((m) => ({ value: m.user_id as number, label: m.name ?? '' }))])
const byStage = computed(() => {
  const c = data.value?.stage_counts ?? []
  const max = Math.max(1, ...c)
  return (data.value?.stages ?? []).map((s, i) => ({ ...s, n: c[i] ?? 0, w: ((c[i] ?? 0) / max) * 100 }))
})
const pct = (n: number) => `${Math.round(n)}%`
const share = (n: number, of: number) => (of ? `${Math.round((n / of) * 1000) / 10}%` : '—')
const sourceOptions = computed(() => [{ value: '', label: t('crm.a.allSources') }, ...sources.items.filter((s) => s.code !== 'return').map((s) => ({ value: s.code, label: srcLabel(s.code) }))])
/** Lead → booked for a trial → came → paid: each step by the lead's history, with its share of all leads and of the step before. */
const conv = computed(() => {
  const x = data.value?.total
  if (!x) return []
  const steps = [{ k: 'new', name: t('crm.a.leads'), n: x.new }, { k: 'trial_booked', name: t('crm.a.booked'), n: x.trial_booked }, { k: 'trial_done', name: t('crm.a.trials'), n: x.trial_done }, { k: 'paid', name: t('crm.a.paid'), n: x.paid }]
  return steps.map((s, i) => ({ ...s, w: x.new ? (s.n / x.new) * 100 : 0, all: share(s.n, x.new), prev: i ? share(s.n, steps[i - 1]!.n) : '' }))
})
const lostKinds = computed(() => {
  const x = data.value
  const lost = x?.total.lost ?? 0
  return (x?.lost_kinds ?? []).map((k) => ({ ...k, w: lost ? (k.count / lost) * 100 : 0, ofLost: share(k.count, lost), ofAll: share(k.count, x?.total.new ?? 0) }))
})
</script>

<template>
  <div class="toolbar">
    <UiInput v-model="f.from" type="date" :max="f.to" class="tb-date" :aria-label="t('payments.from')" />
    <span class="muted">—</span>
    <UiInput v-model="f.to" type="date" :min="f.from" class="tb-date" :aria-label="t('payments.to')" />
    <UiSelect v-model="manager" :options="managerOptions" :label="t('nv.an.manager')" />
    <UiSelect v-model="source" :options="sourceOptions" :label="t('crm.a.source')" />
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
    <div class="grid an-tables" style="margin-bottom: 16px" data-testid="an-conv">
      <UiCard :title="t('crm.a.conv')" icon="funnel">
        <div v-for="r in conv" :key="r.k" class="src-row an-cv">
          <span class="nm">{{ r.name }}</span>
          <span class="tr"><i :style="{ width: `${r.w}%` }" /></span>
          <span class="vv">{{ r.n }}</span>
          <span class="an-p"><b>{{ r.all }}</b> {{ t('crm.a.ofLeads') }}<template v-if="r.prev"> · {{ r.prev }} {{ t('crm.a.ofPrev') }}</template></span>
        </div>
      </UiCard>
      <UiCard :title="t('crm.a.lostReasons')">
        <div v-for="r in lostKinds" :key="r.code" class="src-row an-cv">
          <span class="nm">{{ t(`crm.lostKind.${r.code}`) }}</span>
          <span class="tr"><i :style="{ width: `${r.w}%`, background: 'var(--red)' }" /></span>
          <span class="vv">{{ r.count }}</span>
          <span class="an-p"><b>{{ r.ofLost }}</b> {{ t('crm.a.ofLost') }} · {{ r.ofAll }} {{ t('crm.a.ofLeads') }}</span>
        </div>
      </UiCard>
    </div>
    <div class="grid" style="margin-bottom: 16px">
      <UiCard :title="t('nv.an.byStage')" icon="funnel">
        <div v-for="r in byStage" :key="r.id" class="src-row">
          <span class="nm">{{ r.name }}</span>
          <span class="tr"><i :style="{ width: `${r.w}%`, background: tone(r.color) }" /></span>
          <span class="vv">{{ r.n }}</span>
        </div>
      </UiCard>
    </div>
    <UiCard :title="t('nv.an.managers')" flush>
      <div class="scroll-x">
        <table class="an-mg">
          <thead><tr><th>{{ t('nv.an.manager') }}</th><th v-for="st in data.stages" :key="st.id" class="r">{{ st.name }}</th></tr></thead>
          <tbody class="num">
            <tr v-for="m in data.managers" :key="m.user_id ?? 0" :class="{ on: manager && m.user_id === manager }">
              <td><button v-if="m.user_id" type="button" class="linkbtn" @click="manager = manager === m.user_id ? 0 : m.user_id">{{ m.name }}</button><b v-else>{{ t('crm.unassigned') }}</b></td>
              <td v-for="(n, i) in m.counts" :key="i" class="r">{{ n }}</td>
            </tr>
            <tr v-if="!data.managers.length"><td :colspan="data.stages.length + 1" class="muted">{{ t('crm.noData') }}</td></tr>
          </tbody>
        </table>
      </div>
    </UiCard>
    <div class="grid an-tables">
      <UiCard v-for="tbl in [{ title: t('crm.a.bySource'), rows: bySource }, { title: t('crm.a.byBranch'), rows: byBranch }]" :key="tbl.title" :title="tbl.title" flush>
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

<style scoped>
.an-mg { min-width: 760px }
.an-cv { grid-template-columns: minmax(120px, 210px) minmax(0, 1fr) 44px; row-gap: 2px }
.an-p { grid-column: 1 / -1; font-size: 12px; color: var(--muted) }
.an-p b { color: var(--ink) }
.an-mg th { white-space: nowrap }
.an-mg tr.on td { background: var(--navy-50) }
</style>
