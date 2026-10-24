<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiCard, UiEmptyState, UiIcon, UiSkeleton, UiTabs } from '@/components/ui'
import { portalApi, type PortalMark, type PortalTest } from '@/api/portal'
import { usePortalStore } from '@/stores/portal'
import { useToastStore } from '@/stores/toast'
import { dayLabel, dmy, hm } from '@/utils/dates'
import { apiErr } from '@/utils/err'
import type { Locale } from '@/i18n'

/** Attendance with grades and teacher comments, rating a lesson 1–5 (within 7 days), and test results. */
const { t, locale } = useI18n()
const portal = usePortalStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)
const tab = ref<'attendance' | 'tests'>('attendance')
const tabs = computed(() => [{ value: 'attendance' as const, label: t('portal.tab.attendance') }, { value: 'tests' as const, label: t('portal.tab.tests') }])
const data = ref<{ items: PortalMark[]; month: { lessons: number; present: number; rate: number | null } } | null>(null)
const tests = ref<PortalTest[] | null>(null)
const rating = ref<number | null>(null)
const hover = ref<{ id: number; n: number } | null>(null)

watch(() => portal.child?.id, async (id) => {
  data.value = null
  tests.value = null
  if (!id) return
  const [a, ts] = await Promise.all([portalApi.attendance(id).catch(() => ({ items: [], month: { lessons: 0, present: 0, rate: null } })), portalApi.tests(id).catch(() => [])])
  data.value = a
  tests.value = ts
}, { immediate: true })

const ST = { present: '✓', late: '~', absent: '×', excused: '○' } as const
const canRate = (m: PortalMark) => (m.status === 'present' || m.status === 'late') && Date.now() - new Date(m.at).getTime() < 7 * 86400000
const shown = (m: PortalMark) => (hover.value?.id === m.lesson_id ? hover.value.n : m.my_rating ?? 0)

async function rate(m: PortalMark, stars: number) {
  const id = portal.child?.id
  if (!id) return
  rating.value = m.lesson_id
  try {
    await portalApi.rate(m.lesson_id, { student_id: id, stars })
    m.my_rating = stars
    toast.ok(t('portal.rated'))
  } catch (e) {
    toast.error(apiErr(e) ?? t('errors.generic'))
  } finally {
    rating.value = null
  }
}
const pct = (x: PortalTest) => (x.max_score ? Math.round((x.score / x.max_score) * 100) : null)
</script>

<template>
  <div class="ph"><div><h1>{{ t('portal.nav.progress') }}</h1><p>{{ portal.child?.full_name }}</p></div></div>
  <div class="toolbar"><UiTabs v-model="tab" :items="tabs" :label="t('portal.nav.progress')" /></div>

  <template v-if="tab === 'attendance'">
    <div class="grid fin-k" style="grid-template-columns: repeat(3, minmax(0, 1fr))">
      <div class="card kpi"><div class="k">{{ t('portal.month.rate') }}</div><div class="v num">{{ data ? (data.month.rate === null ? '—' : `${data.month.rate}%`) : '…' }}</div></div>
      <div class="card kpi"><div class="k">{{ t('portal.month.lessons') }}</div><div class="v num">{{ data?.month.lessons ?? '…' }}</div></div>
      <div class="card kpi"><div class="k">{{ t('portal.month.present') }}</div><div class="v num">{{ data?.month.present ?? '…' }}</div></div>
    </div>
    <UiCard>
      <UiSkeleton v-if="!data" :lines="6" />
      <UiEmptyState v-else-if="!data.items.length" icon="attendance" :title="t('portal.noMarks')" />
      <div v-for="m in data?.items ?? []" :key="m.lesson_id" class="p-mark">
        <span class="st" :class="m.status" :title="t(`portal.st.${m.status}`)" aria-hidden="true">{{ ST[m.status] }}</span>
        <div style="min-width: 0">
          <b style="display: block">{{ dayLabel(m.at, loc, { weekday: 'short', day: 'numeric', month: 'short' }) }} · {{ hm(m.at, loc) }}</b>
          <span class="muted" style="font-size: 12.5px">{{ t(`portal.st.${m.status}`) }}<template v-if="m.group"> · {{ m.group }}</template><template v-if="!m.charged && m.status !== 'present' && m.status !== 'late'"> · {{ t('portal.notCharged') }}</template></span>
        </div>
        <div style="display: flex; gap: 6px; align-items: center">
          <span v-if="m.stars" class="coin-v" :title="t('portal.teacherStars')"><UiIcon name="star" :size="14" />{{ m.stars }}</span>
          <span v-if="m.grade !== null" class="grade-pill" :title="t('portal.grade')">{{ m.grade }}</span>
        </div>
        <p v-if="m.comment" class="cm m0 pre">{{ m.comment }}</p>
        <div v-if="canRate(m) || m.my_rating" class="p-rate">
          <span>{{ m.my_rating ? t('portal.yourRating') : t('portal.rateLesson') }}</span>
          <span class="stars" role="radiogroup" :aria-label="t('portal.rateLesson')" @mouseleave="hover = null">
            <button
              v-for="n in 5"
              :key="n"
              type="button"
              role="radio"
              :aria-checked="m.my_rating === n"
              :aria-label="t('portal.starsN', { n })"
              :class="{ on: n <= shown(m) }"
              :disabled="!canRate(m) || rating === m.lesson_id"
              @mouseenter="canRate(m) && (hover = { id: m.lesson_id, n })"
              @click="rate(m, n)"
            ><UiIcon name="star" :size="20" /></button>
          </span>
        </div>
      </div>
    </UiCard>
  </template>

  <UiCard v-else>
    <UiSkeleton v-if="!tests" :lines="4" />
    <UiEmptyState v-else-if="!tests.length" icon="tests" :title="t('portal.noTests')" />
    <div v-for="x in tests ?? []" :key="x.id" class="list-row">
      <span class="grade">{{ x.score }}</span>
      <div class="grow"><b>{{ x.title }}</b><span>{{ t('students.score', { s: x.score, max: x.max_score }) }}<template v-if="pct(x) !== null"> · {{ pct(x) }}%</template> · {{ dmy(x.finished_at, loc) }}</span></div>
    </div>
  </UiCard>
</template>
