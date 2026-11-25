<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import BrandLogo from '@/components/layout/BrandLogo.vue'
import { UiButton, UiIcon, UiSkeleton, UiTextarea } from '@/components/ui'
import { myTestsApi, type MyTestState } from '@/api/assessment'
import { usePortalStore } from '@/stores/portal'
import { nowMs } from '@/utils/clock'
import { apiErr } from '@/utils/err'

/**
 * A group test taken by the student: one question at a time, no way back, the order and the timer live on the server.
 * Leaving the page (another tab, minimised window) annuls the attempt until the teacher restores it.
 */
const { t } = useI18n()
const route = useRoute()
const portal = usePortalStore()

const id = computed(() => Number(route.params.id))
const sid = computed(() => portal.child?.id ?? 0)
const st = ref<MyTestState | null>(null)
const missing = ref(false)
const busy = ref(false)
const error = ref<string | null>(null)
const picked = ref<number[]>([])
const text = ref('')
const tick = ref(nowMs())
let clock: ReturnType<typeof setInterval> | null = null
let poll: ReturnType<typeof setInterval> | null = null

const a = computed(() => st.value?.attempt ?? null)
const q = computed(() => st.value?.question ?? null)
const taking = computed(() => st.value?.status === 'running' && a.value?.status === 'in_progress' && !!q.value)
const view = computed(() => {
  if (missing.value) return 'missing'
  if (!st.value) return 'loading'
  if (a.value?.status === 'void') return 'void'
  if (a.value && (a.value.status === 'done' || a.value.status === 'needs_review')) return 'done'
  if (st.value.status === 'finished') return 'over'
  if (taking.value) return 'test'
  return 'intro'
})
const leftS = computed(() => (st.value?.ends_at ? Math.max(0, Math.ceil((new Date(st.value.ends_at).getTime() - tick.value) / 1000)) : null))
const leftLabel = computed(() => (leftS.value === null ? '' : `${Math.floor(leftS.value / 60)}:${String(leftS.value % 60).padStart(2, '0')}`))
const pct = computed(() => (a.value?.total ? Math.round((a.value.position / a.value.total) * 100) : 0))
const dur = computed(() => {
  const d = a.value?.duration_sec
  return d == null ? '—' : t('nv.gt.min', { m: Math.floor(d / 60), s: d % 60 })
})

function take(s: MyTestState) {
  if (s.question?.id !== st.value?.question?.id) {
    picked.value = []
    text.value = ''
  }
  st.value = s
}
async function load() {
  if (!sid.value) return
  try {
    take(await myTestsApi.state(id.value, sid.value))
  } catch {
    if (!st.value) missing.value = true
  }
}
async function begin() {
  busy.value = true
  error.value = null
  try {
    take(await myTestsApi.begin(id.value, sid.value))
  } catch (e) {
    error.value = apiErr(e) ?? t('errors.generic')
  } finally {
    busy.value = false
  }
}
function pick(i: number) {
  if (!q.value) return
  error.value = null
  picked.value = q.value.kind === 'multi' ? (picked.value.includes(i) ? picked.value.filter((x) => x !== i) : [...picked.value, i]) : [i]
}
async function next() {
  if (!q.value || busy.value) return
  const answer = q.value.kind === 'text' ? text.value.trim() : picked.value
  if (!answer.length) return (error.value = t('nv.gt.pickAnswer'))
  busy.value = true
  error.value = null
  try {
    take(await myTestsApi.answer(id.value, { student_id: sid.value, question_id: q.value.id, answer }))
    window.scrollTo({ top: 0 })
  } catch (e) {
    error.value = apiErr(e) ?? t('errors.generic')
    await load()
  } finally {
    busy.value = false
  }
}

/* ---------- leaving the page annuls the attempt ---------- */
function left() {
  if (!taking.value) return
  if (st.value?.attempt) st.value = { ...st.value, attempt: { ...st.value.attempt, status: 'void' }, question: null }
  myTestsApi.leave(id.value, sid.value).then(take).catch(() => undefined)
}
const onHide = () => document.visibilityState === 'hidden' && left()

onMounted(async () => {
  if (!portal.me) await portal.load()
  if (!sid.value) missing.value = true
  await load()
  document.addEventListener('visibilitychange', onHide)
  window.addEventListener('blur', left)
  window.addEventListener('pagehide', left)
  clock = setInterval(() => (tick.value = nowMs()), 1000)
  /* waits for the teacher: the start, a restore after annulment, the end */
  poll = setInterval(() => !taking.value && st.value?.status !== 'finished' && view.value !== 'done' && view.value !== 'over' && view.value !== 'missing' && load(), 4000)
})
onBeforeUnmount(() => {
  left()
  document.removeEventListener('visibilitychange', onHide)
  window.removeEventListener('blur', left)
  window.removeEventListener('pagehide', left)
  if (clock) clearInterval(clock)
  if (poll) clearInterval(poll)
})
watch(leftS, (v) => v === 0 && taking.value && load())
</script>

<template>
  <div class="pt">
    <header class="pt-top"><BrandLogo :size="34" :tagline="false" /><span class="sp" /></header>
    <main class="pt-main">
      <section v-if="view === 'loading'" class="card pt-card"><UiSkeleton :lines="6" /></section>

      <section v-else-if="view === 'missing'" class="card pt-card pt-center">
        <UiIcon name="tests" :size="40" class="pt-big-ico" />
        <h1>{{ t('nv.gt.notYours') }}</h1>
        <UiButton to="/portal">{{ t('nv.gt.toCabinet') }}</UiButton>
      </section>

      <section v-else-if="view === 'intro' && st" class="card pt-card">
        <h1>{{ st.title }}</h1>
        <p class="pt-meta"><span><UiIcon name="clock" :size="16" />{{ t('nv.gt.introT', { n: st.time_limit_min }) }}</span><span v-if="st.status === 'running' && leftLabel"><UiIcon name="clock" :size="16" />{{ t('nv.gt.left', { t: leftLabel }) }}</span></p>
        <ul class="ptg-rules"><li>{{ t('nv.gt.rule1') }}</li><li>{{ t('nv.gt.rule2') }}</li></ul>
        <p v-if="error" class="form-err" role="alert">{{ error }}</p>
        <UiButton v-if="st.status === 'running'" variant="primary" size="lg" block icon-end="arrow" :loading="busy" @click="begin">{{ t('nv.gt.begin') }}</UiButton>
        <p v-else class="ptg-wait" role="status"><UiIcon name="clock" :size="18" />{{ t('nv.gt.waitStart') }}</p>
      </section>

      <section v-else-if="view === 'test' && q && a" class="card pt-card" :aria-busy="busy">
        <div class="pt-prog">
          <span>{{ t('nv.gt.qOf', { n: a.position + 1, total: a.total }) }}</span>
          <span class="sp" />
          <span v-if="leftLabel" class="chip" :class="{ red: (leftS ?? 0) < 60 }" role="timer"><UiIcon name="clock" :size="16" />{{ t('nv.gt.left', { t: leftLabel }) }}</span>
        </div>
        <div class="bar-track" role="progressbar" :aria-valuenow="pct" aria-valuemin="0" aria-valuemax="100"><i :style="{ width: `${pct}%` }" /></div>
        <Transition name="swap" mode="out-in">
          <fieldset :key="q.id" class="pt-q">
            <legend>{{ q.text }}</legend>
            <p v-if="q.kind === 'multi'" class="form-note">{{ t('placement.multiHint') }}</p>
            <UiTextarea v-if="q.kind === 'text'" v-model="text" :placeholder="t('placement.answerPh')" :aria-label="q.text" :rows="4" :maxlength="2000" />
            <div v-else class="pt-opts">
              <label v-for="(o, i) in q.options" :key="i" class="pt-opt" :class="{ on: picked.includes(i) }">
                <input :type="q.kind === 'multi' ? 'checkbox' : 'radio'" :name="`q${q.id}`" :checked="picked.includes(i)" @change="pick(i)" />
                <span class="pt-mark" :class="q.kind" aria-hidden="true" />
                <span class="pt-otext">{{ o }}</span>
              </label>
            </div>
          </fieldset>
        </Transition>
        <p v-if="error" class="form-err" role="alert">{{ error }}</p>
        <div class="pt-nav"><span class="sp" /><UiButton variant="primary" size="lg" icon-end="arrow" :loading="busy" @click="next">{{ t('nv.gt.next') }}</UiButton></div>
      </section>

      <section v-else-if="view === 'void'" class="card pt-card pt-center" role="alert">
        <span class="pt-done-ico ptg-red"><UiIcon name="lock" :size="40" /></span>
        <h1>{{ t('nv.gt.voidTitle') }}</h1>
        <p class="muted">{{ t('nv.gt.voidText') }}</p>
      </section>

      <section v-else-if="st" class="card pt-card pt-center">
        <span class="pt-done-ico"><UiIcon name="trophy" :size="40" /></span>
        <h1>{{ t('nv.gt.doneTitle') }}</h1>
        <div v-if="a && a.status === 'done'" class="pt-res">
          <div><small>{{ t('nv.gt.yourScore') }}</small><b class="num">{{ a.score }} / {{ a.max_score }}</b></div>
          <div><small>{{ t('nv.gt.yourTime') }}</small><b class="num">{{ dur }}</b></div>
        </div>
        <p v-else-if="a" class="muted">{{ t('nv.gt.reviewText') }}</p>
        <UiButton to="/portal/progress">{{ t('nv.gt.toCabinet') }}</UiButton>
      </section>
    </main>
  </div>
</template>

<style scoped>
.ptg-rules { margin: 0; padding-left: 20px; display: grid; gap: 4px; font-weight: 600 }
.ptg-wait { margin: 0; display: flex; align-items: center; gap: 8px; color: var(--muted) }
.ptg-red { background: var(--red-100); color: var(--red-ink) }
</style>
