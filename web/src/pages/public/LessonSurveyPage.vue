<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import BrandLogo from '@/components/layout/BrandLogo.vue'
import { UiButton, UiIcon, UiSegmented, UiSkeleton, UiTextarea } from '@/components/ui'
import { surveyApi, type PublicSurvey } from '@/api/assessment'
import { useUiStore } from '@/stores/ui'
import type { Locale } from '@/i18n'
import { apiErr } from '@/utils/err'

/** Public «Оценка урока» page opened from the QR in class: no login, a few questions, one answer per phone. */
const { t } = useI18n()
const route = useRoute()
const ui = useUiStore()
const token = computed(() => String(route.params.token ?? ''))
const KEY = computed(() => `oe-lesson-survey:${token.value}`)
type Step = 'loading' | 'missing' | 'closed' | 'form' | 'done'
const step = ref<Step>('loading')
const survey = ref<PublicSurvey | null>(null)
const answers = ref<(number | string | null)[]>([])
const busy = ref(false)
const error = ref('')
const langs = computed<{ value: Locale; label: string }[]>(() => [{ value: 'ru', label: t('lang.ru') }, { value: 'kk', label: t('lang.kk') }])

function sent(): boolean {
  try {
    return localStorage.getItem(KEY.value) === '1'
  } catch {
    return false
  }
}
onMounted(async () => {
  try {
    const s = await surveyApi.get(token.value)
    survey.value = s
    answers.value = s.questions.map(() => null)
    step.value = sent() ? 'done' : s.open ? 'form' : 'closed'
  } catch {
    step.value = 'missing'
  }
})
async function send() {
  const s = survey.value
  if (!s) return
  if (s.questions.some((q, i) => q.kind === 'stars' && !answers.value[i])) {
    error.value = t('nv.sv.needStars')
    return
  }
  busy.value = true
  error.value = ''
  try {
    await surveyApi.answer(token.value, answers.value.map((a) => (typeof a === 'string' ? a.trim() || null : a)))
    try {
      localStorage.setItem(KEY.value, '1')
    } catch {
      /* private mode */
    }
    step.value = 'done'
  } catch (e) {
    error.value = apiErr(e) ?? t('errors.generic')
  } finally {
    busy.value = false
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
      <section v-else-if="step === 'missing' || step === 'closed'" class="card pt-card pt-center">
        <UiIcon name="qr" :size="40" class="pt-big-ico" />
        <h1>{{ step === 'missing' ? t('placement.notFound') : t('nv.sv.closed') }}</h1>
      </section>
      <section v-else-if="step === 'done'" class="card pt-card pt-center">
        <UiIcon name="ok" :size="40" class="pt-big-ico" />
        <h1>{{ t('nv.sv.thanks') }}</h1>
        <p class="muted">{{ t('nv.sv.thanksText') }}</p>
      </section>
      <section v-else-if="survey" class="card pt-card">
        <h1>{{ t('nv.sv.title') }}</h1>
        <p class="pt-meta">
          <span v-if="survey.group"><UiIcon name="groups" :size="16" />{{ survey.group }}</span>
          <span v-if="survey.teacher"><UiIcon name="user" :size="16" />{{ survey.teacher }}</span>
          <span><UiIcon name="clock" :size="16" />{{ survey.lesson }}</span>
        </p>
        <form class="stack" novalidate @submit.prevent="send">
          <div v-for="(q, i) in survey.questions" :key="i" class="sv-ask">
            <b v-if="q.kind === 'stars'">{{ i + 1 }}. {{ q.text }}</b>
            <div v-if="q.kind === 'stars'" class="sv-stars" role="radiogroup" :aria-label="q.text">
              <button v-for="n in 5" :key="n" type="button" role="radio" :aria-checked="answers[i] === n" :class="{ on: typeof answers[i] === 'number' && (answers[i] as number) >= n }" @click="answers[i] = n">★</button>
            </div>
            <UiTextarea v-else :model-value="(answers[i] as string | null) ?? ''" :label="`${i + 1}. ${q.text}`" :rows="3" :maxlength="1000" @update:model-value="(v: string) => (answers[i] = v)" />
          </div>
          <p v-if="error" class="form-err" role="alert">{{ error }}</p>
          <UiButton type="submit" variant="primary" block :loading="busy">{{ t('nv.sv.send') }}</UiButton>
        </form>
      </section>
    </main>
  </div>
</template>
