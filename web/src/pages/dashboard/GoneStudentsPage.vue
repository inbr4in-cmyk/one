<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { UiButton, UiCard, UiEmptyState, UiSkeleton, UiTabs } from '@/components/ui'
import { financeApi, type GoneStudent } from '@/api/finance'
import { useBranchStore } from '@/stores/branch'
import { useRefsStore } from '@/stores/refs'
import { dmy } from '@/utils/dates'
import { periodLabel } from '@/utils/period'
import type { Locale } from '@/i18n'

/** Who left, who is frozen, who waits for a group: when the student came and left, how long and with whom he studied, why he left. */
type Kind = 'left' | 'frozen' | 'waiting'
const { t, locale } = useI18n()
const loc = computed(() => locale.value as Locale)
const route = useRoute()
const router = useRouter()
const branch = useBranchStore()
const refs = useRefsStore()
const kind = computed<Kind>({
  get: () => (['left', 'frozen', 'waiting'].includes(String(route.params.status)) ? (route.params.status as Kind) : 'left'),
  set: (v) => void router.replace({ name: 'dashboard-students', params: { status: v }, query: route.query }),
})
/** Opened from the dashboard: the same day or month as there */
const span = computed(() => {
  const d = String(route.query.day ?? ''), m = String(route.query.month ?? '')
  return /^\d{4}-\d{2}$/.test(m) ? { month: m } : /^\d{4}-\d{2}-\d{2}$/.test(d) ? { day: d } : {}
})
const spanLabel = computed(() => (kind.value === 'waiting' ? '' : span.value.month ? periodLabel(span.value.month, loc.value) : span.value.day ? dmy(span.value.day, loc.value) : ''))
const rows = ref<GoneStudent[] | null>(null)
let seq = 0
async function load() {
  const my = ++seq
  rows.value = null
  const r = await financeApi.students({ branch_id: branch.filterId, status: kind.value, ...span.value }).catch(() => [])
  if (my === seq) rows.value = r
}
watch([kind, () => branch.filterId, span], load, { immediate: true })
const tabs = computed(() => (['left', 'frozen', 'waiting'] as Kind[]).map((k) => ({ value: k, label: t(`nv.dd.g.${k}`), count: k === kind.value ? rows.value?.length : undefined })))
</script>

<template>
  <div class="ph">
    <div><h1>{{ t('nv.dd.goneTitle') }}</h1><p v-if="spanLabel">{{ spanLabel }}</p></div>
    <span class="sp" />
    <UiButton icon="dash" to="/dashboard">{{ t('nav.dashboard') }}</UiButton>
  </div>
  <UiTabs v-model="kind" :items="tabs" :label="t('nv.dd.goneTitle')" />
  <div v-if="!rows" class="card card-pad"><UiSkeleton :lines="6" /></div>
  <UiEmptyState v-else-if="!rows.length" icon="students" :title="t('nv.dd.none')" />
  <UiCard v-else flush>
    <div class="scroll-x">
      <table class="tbl gone">
        <thead><tr>
          <th>{{ t('nv.dd.c.student') }}</th><th>{{ t('nv.dd.c.came') }}</th>
          <th v-if="kind === 'left'">{{ t('nv.dd.c.left') }}</th><th v-if="kind === 'frozen'">{{ t('nv.dd.since') }}</th><th v-if="kind === 'frozen'">{{ t('nv.dd.c.until') }}</th>
          <th class="r">{{ t('nv.dd.c.months') }}</th><th>{{ t('nv.dd.c.teacher') }}</th><th v-if="kind !== 'waiting'">{{ t('nv.dd.c.reason') }}</th>
        </tr></thead>
        <tbody>
          <tr v-for="x in rows" :key="x.id">
            <td><RouterLink :to="`/students/${x.id}`"><b>{{ x.full_name }}</b></RouterLink><small v-if="branch.filterId === null" class="muted gone-br">{{ refs.branchName(x.branch_id) }}</small></td>
            <td class="num">{{ x.came ? dmy(x.came, loc) : '—' }}</td>
            <td v-if="kind === 'left'" class="num">{{ x.left ? dmy(x.left, loc) : '—' }}</td>
            <td v-if="kind === 'frozen'" class="num">{{ x.since ? dmy(x.since, loc) : '—' }}</td>
            <td v-if="kind === 'frozen'" class="num">{{ x.until ? dmy(x.until, loc) : '—' }}</td>
            <td class="r num">{{ x.months ?? '—' }}</td>
            <td>{{ x.teachers.join(', ') || '—' }}</td>
            <td v-if="kind !== 'waiting'">{{ x.reason || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </UiCard>
</template>

<style scoped>
.gone { min-width: 760px }
.gone th { white-space: nowrap }
.gone-br { display: block; font-size: 12px }
</style>
