<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import BrandLogo from '@/components/layout/BrandLogo.vue'
import { UiButton, UiCheck, UiIcon, UiInput, UiPhoneInput, UiSegmented, UiSkeleton, UiTextarea } from '@/components/ui'
import { ApiError } from '@/api/http'
import { placementApi, type Answers, type PlacementResult, type PublicTest } from '@/api/assessment'
import { useUiStore } from '@/stores/ui'
import type { Locale } from '@/i18n'
import { apiErr } from '@/utils/err'

/**
 * Public QR placement test (ТЗ 6), no login: the candidate leaves a name and phone, answers, sees the result.
 * The server scores it and creates or updates the lead. Progress survives a reload (sessionStorage, this tab only).
 */
type Step = 'loading' | 'missing' | 'intro' | 'test' | 'sending' | 'done'

const { t } = useI18n()
const route = useRoute()
const ui = useUiStore()
const token = computed(() => String(route.params.token ?? ''))
const KEY = computed(() => `oe-placement:${token.value}`)

const step = ref<Step>('loading')
const test = ref<PublicTest | null>(null)
const form = reactive({ name: '', phone: '', age: '', parent_name: '', parent_phone: '', consent: false })
const errors = reactive<{ name?: string; phone?: string; consent?: string; form?: string }>({})
const busy = ref(false)
const attemptToken = ref('')
const startedAt = ref(0)
const answers = reactive<Answers>({})
const idx = ref(0)
const result = ref<PlacementResult | null>(null)
const now = ref(Date.now())
let timer: ReturnType<typeof setInterval> | null = null

const langs = computed<{ value: Locale; label: string }[]>(() => [
  { value: 'ru', label: t('lang.ru') },
  { value: 'kk', label: t('lang.kk') },
])
const questions = computed(() => test.value?.questions ?? [])
const q = computed(() => questions.value[idx.value] ?? null)
const ageNum = computed(() => (form.age.trim() ? Number(form.age) : null))
const isChild = computed(() => ageNum.value !== null && ageNum.value < 18)
const answered = (id: number) => {
  const a = answers[String(id)]
  return Array.isArray(a) ? a.length > 0 : typeof a === 'string' && a.trim().length > 0
}
const unanswered = computed(() => questions.value.filter((x) => !answered(x.id)).length)
const pct = computed(() => (questions.value.length ? Math.round(((idx.value + 1) / questions.value.length) * 100) : 0))
const deadline = computed(() => (test.value?.time_limit_min && startedAt.value ? startedAt.value + test.value.time_limit_min * 60_000 : null))
const leftMs = computed(() => (deadline.value ? Math.max(0, deadline.value - now.value) : null))
const leftLabel = computed(() => {
  if (leftMs.value === null) return ''
  const s = Math.ceil(leftMs.value / 1000)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
})

/* ---------- this tab's progress ---------- */
function save() {
  try {
    sessionStorage.setItem(KEY.value, JSON.stringify({ attemptToken: attemptToken.value, startedAt: startedAt.value, answers, idx: idx.value }))
  } catch {
    /* private mode: progress just isn't kept */
  }
}
function restore(): boolean {
  try {
    const raw = sessionStorage.getItem(KEY.value)
    if (!raw) return false
    const s = JSON.parse(raw) as { attemptToken?: string; startedAt?: number; answers?: Answers; idx?: number }
    if (!s.attemptToken) return false
    attemptToken.value = s.attemptToken
    startedAt.value = s.startedAt ?? Date.now()
    Object.assign(answers, s.answers ?? {})
    idx.value = Math.min(Math.max(0, s.idx ?? 0), Math.max(0, questions.value.length - 1))
    return true
  } catch {
    return false
  }
}
function forget() {
  try {
    sessionStorage.removeItem(KEY.value)
  } catch {
    /* ignore */
  }
}

onMounted(async () => {
  try {
    test.value = await placementApi.get(token.value)
    document.title = `${t('placement.title')} · One English`
    if (restore()) startTest(false)
    else step.value = 'intro'
  } catch {
    step.value = 'missing'
  }
})
onBeforeUnmount(() => timer && clearInterval(timer))
watch([answers, idx], () => step.value === 'test' && save(), { deep: true })
watch(leftMs, (v) => {
  if (v === 0 && step.value === 'test') submit(true)
})

/* ---------- intro ---------- */
async function begin() {
  errors.name = form.name.trim().length < 2 ? t('placement.nameRequired') : undefined
  errors.phone = form.phone ? undefined : t('placement.phoneRequired')
  errors.consent = form.consent ? undefined : t('placement.consentRequired')
  errors.form = undefined
  if (errors.name || errors.phone || errors.consent) return
  busy.value = true
  try {
    const r = await placementApi.start(token.value, {
      name: form.name.trim(),
      phone: form.phone,
      age: ageNum.value !== null && Number.isFinite(ageNum.value) ? Math.round(ageNum.value) : null,
      parent_name: isChild.value && form.parent_name.trim() ? form.parent_name.trim() : null,
      parent_phone: isChild.value && form.parent_phone ? form.parent_phone : null,
      consent: form.consent,
    })
    attemptToken.value = r.attempt_token
    startedAt.value = Date.now()
    startTest(true)
  } catch (e) {
    errors.form = apiErr(e) ?? t('errors.generic')
  } finally {
    busy.value = false
  }
}

function startTest(fresh: boolean) {
  if (fresh) idx.value = 0
  step.value = 'test'
  save()
  if (test.value?.time_limit_min && !timer) timer = setInterval(() => (now.value = Date.now()), 1000)
}

/* ---------- answering ---------- */
function pick(i: number) {
  const cur = q.value
  if (!cur) return
  const key = String(cur.id)
  if (cur.kind === 'multi') {
    const prev = Array.isArray(answers[key]) ? (answers[key] as number[]) : []
    answers[key] = prev.includes(i) ? prev.filter((x) => x !== i) : [...prev, i].sort((a, b) => a - b)
  } else {
    answers[key] = [i]
  }
}
const isPicked = (i: number) => {
  const a = q.value ? answers[String(q.value.id)] : undefined
  return Array.isArray(a) && a.includes(i)
}
const textAnswer = computed({
  get: () => {
    const a = q.value ? answers[String(q.value.id)] : undefined
    return typeof a === 'string' ? a : ''
  },
  set: (v: string) => {
    if (q.value) answers[String(q.value.id)] = v
  },
})
function go(d: number) {
  idx.value = Math.min(Math.max(0, idx.value + d), questions.value.length - 1)
  document.querySelector('.pt-main')?.scrollIntoView({ block: 'start' })
}

async function submit(timeUp = false) {
  if (step.value !== 'test') return
  if (!timeUp && unanswered.value > 0 && !window.confirm(t('placement.unanswered', { n: unanswered.value }))) return
  step.value = 'sending'
  if (timer) clearInterval(timer)
  timer = null
  // Only real answers go out, in the shape the router scores.
  const out: Answers = {}
  for (const x of questions.value) {
    const a = answers[String(x.id)]
    if (Array.isArray(a) && a.length) out[String(x.id)] = a
    else if (typeof a === 'string' && a.trim()) out[String(x.id)] = a.trim().slice(0, 2000)
  }
  try {
    result.value = await placementApi.submit(attemptToken.value, out)
    forget()
    step.value = 'done'
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 400)) {
      forget()
      Object.keys(answers).forEach((k) => delete answers[k])
      errors.form = e.status === 401 ? t('placement.expired') : (apiErr(e) ?? t('errors.generic'))
      step.value = 'intro'
    } else {
      errors.form = apiErr(e) ?? t('errors.generic')
      step.value = 'test'
    }
  }
}
</script>

<template>
  <div class="pt">
    <header class="pt-top">
      <BrandLogo :size="34" :tagline="false" />
      <span class="sp" />
      <UiSegmented v-model="ui.locale" :options="langs" :label="t('user.language')" size="sm" />
    </header>

    <main class="pt-main">
      <section v-if="step === 'loading'" class="card pt-card"><UiSkeleton :lines="6" /></section>

      <section v-else-if="step === 'missing'" class="card pt-card pt-center">
        <UiIcon name="qr" :size="40" class="pt-big-ico" />
        <h1>{{ t('placement.notFound') }}</h1>
        <p class="muted">{{ t('placement.notFoundText') }}</p>
      </section>

      <section v-else-if="step === 'intro' && test" class="card pt-card">
        <h1>{{ test.title || t('placement.title') }}</h1>
        <p class="pt-meta">
          <span v-if="test.branch"><UiIcon name="pin" :size="16" />{{ t('placement.branch', { name: test.branch }) }}</span>
          <span><UiIcon name="tests" :size="16" />{{ t('placement.questionsN', { n: questions.length }) }}</span>
          <span v-if="test.time_limit_min"><UiIcon name="clock" :size="16" />{{ t('placement.minutes', { n: test.time_limit_min }) }}</span>
        </p>
        <p class="muted pt-intro">{{ t('placement.intro') }}</p>
        <form class="stack" novalidate @submit.prevent="begin">
          <UiInput v-model="form.name" :label="t('placement.name')" :placeholder="t('placement.namePh')" autocomplete="name" :maxlength="120" :error="errors.name" />
          <UiPhoneInput v-model="form.phone" :label="t('placement.phone')" :hint="t('placement.phoneHint')" :error="errors.phone" />
          <UiInput v-model="form.age" type="number" inputmode="numeric" :min="3" :max="99" :label="t('placement.age')" :placeholder="t('placement.agePh')" />
          <template v-if="isChild">
            <p class="form-note">{{ t('placement.childHint') }}</p>
            <UiInput v-model="form.parent_name" :label="t('placement.parentName')" :maxlength="120" />
            <UiPhoneInput v-model="form.parent_phone" :label="t('placement.parentPhone')" />
          </template>
          <div>
            <UiCheck v-model="form.consent" :label="t('placement.consent')" :hint="t('placement.consentHint')" />
            <p v-if="errors.consent" class="form-err" role="alert" style="margin: 6px 0 0">{{ errors.consent }}</p>
          </div>
          <p v-if="errors.form" class="form-err" role="alert">{{ errors.form }}</p>
          <UiButton type="submit" variant="primary" size="lg" block icon-end="arrow" :loading="busy">{{ t('placement.start') }}</UiButton>
        </form>
      </section>

      <section v-else-if="(step === 'test' || step === 'sending') && q" class="card pt-card" :aria-busy="step === 'sending'">
        <div class="pt-prog">
          <span>{{ t('placement.qOf', { n: idx + 1, total: questions.length }) }}</span>
          <span class="sp" />
          <span v-if="leftLabel" class="chip" :class="{ red: (leftMs ?? 0) < 60_000 }" role="timer"><UiIcon name="clock" :size="16" />{{ t('placement.timeLeft', { t: leftLabel }) }}</span>
        </div>
        <div class="bar-track" role="progressbar" :aria-valuenow="pct" aria-valuemin="0" aria-valuemax="100" :aria-label="t('placement.qOf', { n: idx + 1, total: questions.length })"><i :style="{ width: `${pct}%` }" /></div>

        <Transition name="swap" mode="out-in">
          <fieldset :key="q.id" class="pt-q">
            <legend>{{ q.text }}</legend>
            <p v-if="q.kind === 'multi'" class="form-note">{{ t('placement.multiHint') }}</p>
            <UiTextarea v-if="q.kind === 'text'" v-model="textAnswer" :placeholder="t('placement.answerPh')" :aria-label="q.text" :rows="4" :maxlength="2000" />
            <div v-else class="pt-opts">
              <label v-for="(o, i) in q.options" :key="i" class="pt-opt" :class="{ on: isPicked(i) }">
                <input :type="q.kind === 'multi' ? 'checkbox' : 'radio'" :name="`q${q.id}`" :checked="isPicked(i)" @change="pick(i)" />
                <span class="pt-mark" :class="q.kind" aria-hidden="true" />
                <span class="pt-otext">{{ o }}</span>
              </label>
            </div>
          </fieldset>
        </Transition>

        <p v-if="errors.form" class="form-err" role="alert">{{ errors.form }}</p>
        <div class="pt-nav">
          <UiButton v-if="idx > 0" variant="ghost" icon="arrow" class="flip" :disabled="step === 'sending'" @click="go(-1)">{{ t('placement.prev') }}</UiButton>
          <span class="sp" />
          <UiButton v-if="idx < questions.length - 1" variant="navy" icon-end="arrow" :disabled="step === 'sending'" @click="go(1)">{{ t('placement.next') }}</UiButton>
          <UiButton v-else variant="primary" icon="ok" :loading="step === 'sending'" @click="submit()">{{ t('placement.finish') }}</UiButton>
        </div>
      </section>

      <section v-else-if="step === 'done' && result" class="card pt-card pt-center">
        <span class="pt-done-ico"><UiIcon name="trophy" :size="40" /></span>
        <h1>{{ t('placement.doneTitle') }}</h1>
        <div class="pt-res">
          <div><small>{{ t('placement.scoreLabel') }}</small><b class="num">{{ t('placement.score', { score: result.score, max: result.max }) }}</b></div>
          <div><small>{{ t('placement.levelLabel') }}</small><b>{{ result.level ?? t('placement.levelUnknown') }}</b></div>
        </div>
        <p class="muted">{{ t('placement.doneText') }}</p>
      </section>
    </main>
    <footer class="pt-foot">{{ t('app.footer') }}</footer>
  </div>
</template>
