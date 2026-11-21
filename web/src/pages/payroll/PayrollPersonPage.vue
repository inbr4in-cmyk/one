<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { UiAvatar, UiButton, UiCard, UiEmptyState, UiPeriod, UiSkeleton } from '@/components/ui'
import SettleModal from '@/components/ops/SettleModal.vue'
import { payrollApi, type PayPerson, type PayPersonGroup } from '@/api/payroll'
import { useAuthStore } from '@/stores/auth'
import { useBranchStore } from '@/stores/branch'
import { dmy, money } from '@/utils/dates'
import { periodOf } from '@/utils/period'
import { intlLocale, type Locale } from '@/i18n'

/** Salary page of one staff member: lessons of the month as a grid (groups × days), then the other lines and payouts. */
const { t, te, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const branch = useBranchStore()
const loc = computed(() => locale.value as Locale)
const userId = computed(() => Number(route.params.id))
const period = ref(typeof route.query.period === 'string' && /^\d{4}-\d{2}$/.test(route.query.period) ? route.query.period : periodOf())
const data = ref<PayPerson | null>(null)
const failed = ref(false)
const settleOpen = ref(false)

async function load() {
  data.value = null
  failed.value = false
  try {
    data.value = await payrollApi.person({ period: period.value, user_id: userId.value, branch_id: branch.filterId })
  } catch {
    failed.value = true
  }
}
watch(() => [userId.value, period.value, branch.filterId], load, { immediate: true })
watch(period, (p) => router.replace({ query: { ...route.query, period: p } }))

const days = computed(() => {
  const [y, m] = period.value.split('-').map(Number) as [number, number]
  return Array.from({ length: data.value?.days ?? 0 }, (_, i) => {
    const d = new Date(y, m - 1, i + 1)
    return { n: i + 1, wd: d.toLocaleDateString(intlLocale(loc.value), { weekday: 'short' }), sun: d.getDay() === 0 }
  })
})
function cell(g: PayPersonGroup, day: number) {
  const ls = g.lessons.filter((l) => l.day === day)
  if (!ls.length) return null
  return { amount: ls.reduce((s, l) => s + l.amount, 0), count: ls.length, tip: ls.map((l) => `${l.time} · ${l.note}`).join('\n') }
}
const dayTotal = (day: number) => (data.value?.groups ?? []).reduce((s, g) => s + g.lessons.filter((l) => l.day === day).reduce((x, l) => x + l.amount, 0), 0)
const short = (n: number) => n.toLocaleString(intlLocale(loc.value))
const kindLabel = (k: string) => (te(`payroll.kind.${k}`) ? t(`payroll.kind.${k}`) : k)
const formatLabel = (k: string) => (te(`nv.payp.format.${k}`) ? t(`nv.payp.format.${k}`) : k)
const signed = (n: number) => (n > 0 ? '+' : '') + money(n, loc.value)
const canSettle = computed(() => auth.can('payroll.adjust') && (userId.value !== auth.user?.id || auth.user?.roles.includes('owner')))
</script>

<template>
  <div class="crumbs"><RouterLink to="/payroll">{{ t('nav.payroll') }}</RouterLink> / {{ data?.user.full_name ?? '…' }}</div>
  <UiEmptyState v-if="failed" icon="salary" :title="t('nv.payp.notFound')" />
  <template v-else>
    <div class="ph">
      <UiAvatar v-if="data" :name="data.user.full_name" size="lg" />
      <div><h1>{{ data?.user.full_name ?? '…' }}</h1><p>{{ data?.user.position ?? '' }}</p></div>
      <span class="sp" />
      <UiPeriod v-model="period" />
      <UiButton v-if="canSettle" variant="primary" icon="wallet" @click="settleOpen = true">{{ t('nv.settle.btn') }}</UiButton>
    </div>
    <UiSkeleton v-if="!data" :lines="8" />
    <template v-else>
      <div class="pp-tiles">
        <div class="pp-tile main"><span>{{ t('nv.payp.total') }}</span><b class="num">{{ money(data.total, loc) }}</b></div>
        <div class="pp-tile"><span>{{ t('nv.payp.lessons', { n: data.lessons_count }) }}</span><b class="num">{{ money(data.lessons_total, loc) }}</b></div>
        <div class="pp-tile"><span>{{ t('nv.payp.other') }}</span><b class="num">{{ money(data.other_total, loc) }}</b></div>
        <div class="pp-tile"><span>{{ t('nv.payp.paid') }}</span><b class="num">{{ money(data.paid, loc) }}</b></div>
        <div class="pp-tile"><span>{{ t('nv.payp.left') }}</span><b class="num" :class="data.left > 0 ? 'okc' : undefined">{{ money(data.left, loc) }}</b></div>
      </div>

      <UiCard :title="t('nv.payp.byGroup')" flush>
        <div v-if="data.groups.length" class="pp-wrap">
          <table class="pp-grid">
            <thead>
              <tr>
                <th class="g">{{ t('nv.payp.group') }}</th>
                <th class="tot">{{ t('fin.total') }}</th>
                <th v-for="d in days" :key="d.n" :class="{ sun: d.sun }"><b>{{ d.n }}</b><span>{{ d.wd }}</span></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="g in data.groups" :key="g.key">
                <th class="g">
                  <RouterLink v-if="g.group_id && auth.can('schedule.view')" :to="`/groups/${g.group_id}`">{{ g.name }}</RouterLink>
                  <template v-else>{{ g.name }}</template>
                  <span>{{ formatLabel(g.kind) }} · {{ t('nv.payp.nLessons', { n: g.count }) }}</span>
                </th>
                <td class="tot num">{{ short(g.amount) }}</td>
                <td v-for="d in days" :key="d.n" :class="{ sun: d.sun }">
                  <template v-for="c in [cell(g, d.n)]" :key="0">
                    <span v-if="c" class="pp-cell num" :class="{ zero: c.amount === 0 }" :title="c.tip">{{ short(c.amount) }}<i v-if="c.count > 1">×{{ c.count }}</i></span>
                  </template>
                </td>
              </tr>
            </tbody>
            <tfoot>
              <tr>
                <th class="g">{{ t('nv.payp.perDay') }}</th>
                <td class="tot num">{{ short(data.lessons_total) }}</td>
                <td v-for="d in days" :key="d.n" class="num" :class="{ sun: d.sun }">{{ dayTotal(d.n) ? short(dayTotal(d.n)) : '' }}</td>
              </tr>
            </tfoot>
          </table>
        </div>
        <UiEmptyState v-else icon="cal" :title="t('nv.payp.noLessons')" />
      </UiCard>

      <div class="pp-two">
        <UiCard :title="t('nv.payp.otherLines')" flush>
          <div v-if="data.other.length" class="card-b lr-list">
            <div v-for="a in data.other" :key="a.id" class="list-row">
              <div class="grow"><b>{{ kindLabel(a.kind) === a.kind ? a.title : kindLabel(a.kind) }}</b><span>{{ a.description }} · {{ dmy(a.created_at, loc) }}</span></div>
              <b class="num" :class="a.amount < 0 ? 'redc' : undefined">{{ signed(a.amount) }}</b>
            </div>
          </div>
          <UiEmptyState v-else icon="salary" :title="t('nv.payp.noOther')" />
        </UiCard>
        <UiCard :title="t('nv.payp.payouts')" flush>
          <div v-if="data.payouts.length" class="card-b lr-list">
            <div v-for="b in data.payouts" :key="b.id" class="list-row">
              <div class="grow"><b>{{ dmy(b.paid_on, loc) }}</b><span>{{ b.lines.map((l) => `${l.title} ${money(l.amount, loc)}`).join(' · ') }}<template v-if="b.note"> · {{ b.note }}</template></span></div>
              <b class="num">{{ money(b.total, loc) }}</b>
            </div>
          </div>
          <UiEmptyState v-else icon="wallet" :title="t('nv.payp.noPayouts')" />
        </UiCard>
      </div>
    </template>
  </template>
  <SettleModal v-model:open="settleOpen" :period="period" :user-id="userId" @saved="load" />
</template>

<style scoped>
.crumbs { color: var(--muted); font-size: 13px; margin-bottom: 10px }
.crumbs a { color: inherit }
.pp-tiles { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px }
.pp-tile { background: var(--surface); border: 1px solid var(--line); border-radius: 14px; padding: 12px 14px; display: flex; flex-direction: column; gap: 4px }
.pp-tile span { color: var(--muted); font-size: 12px }
.pp-tile b { font-size: 20px }
.pp-tile.main { background: var(--navy); border-color: var(--navy); color: #fff }
.pp-tile.main span { color: rgba(255, 255, 255, .75) }
.pp-wrap { overflow-x: auto }
.pp-grid { border-collapse: separate; border-spacing: 0; width: max-content; min-width: 100%; font-size: 12px }
.pp-grid th, .pp-grid td { border-bottom: 1px solid var(--line); border-right: 1px solid var(--line); padding: 6px 4px; text-align: center; min-width: 46px; height: 44px }
.pp-grid thead th { background: var(--navy-50); font-weight: 500; color: var(--muted) }
.pp-grid thead th b { display: block; color: var(--ink); font-size: 13px }
.pp-grid thead th span { font-size: 10px; text-transform: lowercase }
.pp-grid .g { position: sticky; left: 0; z-index: 2; background: var(--surface); text-align: left; min-width: 190px; max-width: 220px; padding: 6px 12px; font-weight: 600; font-size: 13px }
.pp-grid thead .g, .pp-grid tfoot .g { background: var(--navy-50) }
.pp-grid .g span { display: block; font-weight: 400; font-size: 11px; color: var(--muted) }
.pp-grid .g a { color: var(--ink) }
.pp-grid .tot { position: sticky; left: 190px; z-index: 2; background: var(--surface); font-weight: 700; min-width: 76px; font-size: 13px }
.pp-grid thead .tot, .pp-grid tfoot .tot, .pp-grid tfoot td { background: var(--navy-50); font-weight: 600 }
.pp-grid .sun { background: color-mix(in srgb, var(--red) 5%, var(--surface)) }
.pp-cell { display: inline-flex; flex-direction: column; align-items: center; background: color-mix(in srgb, var(--ok) 14%, var(--surface)); color: var(--ink); border-radius: 8px; padding: 3px 5px; font-weight: 600; line-height: 1.1 }
.pp-cell.zero { background: var(--navy-50); color: var(--muted); font-weight: 500 }
.pp-cell i { font-style: normal; font-size: 10px; color: var(--muted); font-weight: 500 }
.pp-two { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px }
@media (max-width: 900px) {
  .pp-tiles { grid-template-columns: repeat(2, minmax(0, 1fr)) }
  .pp-tiles .main { grid-column: 1 / -1 }
  .pp-two { grid-template-columns: 1fr }
  .pp-grid .g { min-width: 130px; max-width: 130px }
  .pp-grid .tot { left: 130px }
}
</style>
