<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { UiButton, UiCard, UiChip, UiEmptyState, UiField, UiIcon, UiInput, UiSkeleton } from '@/components/ui'
import { sessionsApi, type SessionBoard, type SessionRow } from '@/api/assessment'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import { nowMs } from '@/utils/clock'
import { dayLabel, hm } from '@/utils/dates'
import type { Locale } from '@/i18n'

/** A group's test at a lesson: the teacher starts it with a timer, watches the students, restores an annulled attempt. */
const { t, locale } = useI18n()
const loc = computed(() => locale.value as Locale)
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const toast = useToastStore()

const id = computed(() => Number(route.params.id))
const b = ref<SessionBoard | null>(null)
const missing = ref(false)
const minutes = ref('60')
const busy = ref(false)
const tick = ref(nowMs())
let poll: ReturnType<typeof setInterval> | null = null
let clock: ReturnType<typeof setInterval> | null = null

async function load() {
  try {
    b.value = await sessionsApi.get(id.value)
  } catch {
    if (!b.value) missing.value = true
  }
}
onMounted(async () => {
  await load()
  if (b.value?.status === 'planned') minutes.value = String(b.value.suggested_min ?? (b.value.time_limit_min || 60))
  poll = setInterval(() => b.value?.status !== 'finished' && document.visibilityState === 'visible' && load(), 5000)
  clock = setInterval(() => (tick.value = nowMs()), 1000)
})
onBeforeUnmount(() => {
  if (poll) clearInterval(poll)
  if (clock) clearInterval(clock)
})

const link = computed(() => new URL(router.resolve(`/portal/test/${id.value}`).href, window.location.href).href)
const left = computed(() => {
  if (b.value?.status !== 'running' || !b.value.ends_at) return ''
  const s = Math.max(0, Math.ceil((new Date(b.value.ends_at).getTime() - tick.value) / 1000))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
})
const dur = (r: SessionRow) => (r.duration_sec == null ? '—' : t('nv.gt.min', { m: Math.floor(r.duration_sec / 60), s: r.duration_sec % 60 }))
const tone = (r: SessionRow) => (r.status === 'done' ? 'ok' : r.status === 'void' ? 'red' : r.status === 'in_progress' ? 'info' : r.status === 'needs_review' ? 'warn' : undefined)
const rows = computed(() => [...(b.value?.rows ?? [])].sort((x, y) => (x.place ?? 999) - (y.place ?? 999) || x.full_name.localeCompare(y.full_name)))

async function act(fn: () => Promise<SessionBoard>, ok?: string) {
  busy.value = true
  try {
    b.value = await fn()
    if (ok) toast.ok(ok)
  } catch {
    /* toast shown by the client */
  } finally {
    busy.value = false
  }
}
function start() {
  const m = Math.round(Number(minutes.value))
  if (!Number.isFinite(m) || m < 5 || m > 300) return toast.error('5–300')
  act(() => sessionsApi.start(id.value, m))
}
const finish = () => window.confirm(t('nv.gt.finishAsk')) && act(() => sessionsApi.finish(id.value))
const restore = (r: SessionRow) => act(() => sessionsApi.restore(id.value, r.student_id), t('nv.gt.restored'))
async function cancel() {
  if (!window.confirm(t('nv.gt.cancelAsk'))) return
  await sessionsApi.remove(id.value).then(() => router.replace('/tests')).catch(() => undefined)
}
async function copy() {
  try {
    await navigator.clipboard.writeText(link.value)
    toast.ok(t('common.copied'))
  } catch {
    toast.error(t('errors.generic'))
  }
}
</script>

<template>
  <UiEmptyState v-if="missing" large icon="tests" :title="t('nv.gt.notYours')" />
  <div v-else-if="!b" class="card card-pad"><UiSkeleton :lines="6" /></div>
  <div v-else class="grid">
    <UiCard>
      <div class="gs-head">
        <span class="gs-ico"><UiIcon name="tests" :size="24" /></span>
        <div class="grow">
          <h2 class="h-display gs-title">{{ b.title }}</h2>
          <p class="m0 muted">{{ b.group_name }}<template v-if="b.lesson_at"> · {{ dayLabel(b.lesson_at, loc, { weekday: 'short', day: 'numeric', month: 'long' }) }}, {{ hm(b.lesson_at, loc) }}</template> · {{ t('tests.questionsN', { n: b.questions }) }}</p>
        </div>
        <UiChip :tone="b.status === 'running' ? 'ok' : b.status === 'planned' ? 'info' : undefined">{{ t(`nv.gt.st.${b.status}`) }}</UiChip>
      </div>

      <div v-if="b.status === 'planned' && b.can_run" class="gs-run">
        <UiField :label="t('nv.gt.timer')" style="max-width: 200px"><UiInput v-model="minutes" type="number" inputmode="numeric" :min="5" :max="300" :aria-label="t('nv.gt.timer')" /></UiField>
        <UiButton variant="primary" icon="ok" :loading="busy" @click="start">{{ t('nv.gt.start') }}</UiButton>
        <span class="sp" />
        <UiButton v-if="auth.can('tests.review')" variant="ghost" icon="trash" @click="cancel">{{ t('nv.gt.cancel') }}</UiButton>
      </div>
      <div v-else-if="b.status === 'running'" class="gs-run">
        <span class="gs-left num" role="timer"><UiIcon name="clock" :size="20" />{{ t('nv.gt.left', { t: left }) }}</span>
        <span class="sp" />
        <UiButton v-if="b.can_run" variant="primary" :loading="busy" @click="finish">{{ t('nv.gt.finish') }}</UiButton>
      </div>

      <div v-if="b.status !== 'finished'" class="gs-link">
        <small>{{ t('nv.gt.link') }}</small>
        <div class="row-actions"><span class="qr-link grow">{{ link }}</span><UiButton size="sm" icon="clip" @click="copy">{{ t('tests.qr.copy') }}</UiButton></div>
      </div>
    </UiCard>

    <p v-if="b.threshold && b.checked" class="gs-sum" :class="b.low ? 'low' : 'ok'" data-testid="gs-sum">{{ t('nv.gt.below', { limit: b.threshold, n: b.low ?? 0, m: b.checked }) }}</p>
    <UiCard flush>
      <div class="gs-table-wrap">
        <table class="tbl gs-table">
          <thead><tr><th>{{ t('nv.gt.place') }}</th><th>{{ t('nv.gt.student') }}</th><th>{{ t('nv.gt.state') }}</th><th>{{ t('nv.gt.answered') }}</th><th>{{ t('nv.gt.score') }}</th><th>{{ t('nv.gt.time') }}</th><th /></tr></thead>
          <tbody>
            <tr v-for="r in rows" :key="r.student_id">
              <td class="num"><b v-if="r.place">{{ r.place }}</b><span v-else class="muted">—</span></td>
              <td><RouterLink :to="`/students/${r.student_id}`">{{ r.full_name }}</RouterLink><small v-if="!r.has_login" class="gs-nologin">{{ t('nv.gt.noLogin') }}</small></td>
              <td><UiChip small :tone="tone(r)">{{ t(`nv.gt.rs.${r.status}`) }}</UiChip></td>
              <td class="num">{{ r.answered }} / {{ b.questions }}</td>
              <td class="num"><b v-if="r.score != null && r.status === 'done' && b.threshold" class="gs-zone" :class="r.low ? 'low' : 'ok'">{{ r.score }} / {{ b.max_score }}</b><template v-else>{{ r.score == null ? '—' : `${r.score} / ${b.max_score}` }}</template></td>
              <td class="num">{{ dur(r) }}</td>
              <td><UiButton v-if="r.attempt_id && b.can_run && (r.status === 'needs_review' || r.status === 'done')" size="sm" :variant="r.status === 'needs_review' ? 'primary' : 'ghost'" :to="`/tests/attempts/${r.attempt_id}`">{{ t('nv.gt.check') }}</UiButton>
                <UiButton v-if="r.status === 'void' && b.status === 'running' && b.can_run" size="sm" variant="primary" :disabled="busy" @click="restore(r)">{{ t('nv.gt.restore') }}</UiButton></td>
            </tr>
          </tbody>
        </table>
      </div>
    </UiCard>
  </div>
</template>

<style scoped>
.gs-zone { display: inline-block; padding: 2px 10px; border-radius: 999px }
.gs-zone.ok, .gs-sum.ok { background: var(--ok-bg); color: var(--ok) }
.gs-zone.low, .gs-sum.low { background: var(--red-100); color: var(--red-ink) }
.gs-sum { margin: 0 0 12px; padding: 10px 14px; border-radius: 12px; font-weight: 600 }
.gs-head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap }
.gs-ico { width: 44px; height: 44px; border-radius: 12px; display: grid; place-items: center; background: var(--navy-50); color: var(--accent-ink); flex: none }
.gs-title { font-size: 20px; margin: 0 }
.gs-run { display: flex; align-items: flex-end; gap: 12px; flex-wrap: wrap; margin-top: 16px }
.gs-left { display: inline-flex; align-items: center; gap: 8px; font-family: var(--font-display); font-size: 24px; font-weight: 600 }
.gs-link { margin-top: 16px; display: grid; gap: 6px }
.gs-link small { color: var(--muted); font-size: 12.5px }
.gs-table-wrap { overflow-x: auto }
.gs-table { width: 100%; min-width: 640px }
.gs-nologin { display: block; color: var(--red-ink); font-size: 12px }
</style>
