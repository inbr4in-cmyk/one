<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import BrandLogo from '@/components/layout/BrandLogo.vue'
import { UiButton, UiIcon, UiInput, UiPhoneInput, UiSelect, UiSkeleton, UiTextarea } from '@/components/ui'
import { formsApi, type FormAnswers, type FormQuestion, type FormSection, type PublicForm } from '@/api/forms'
import { useAuthStore } from '@/stores/auth'
import { apiErr } from '@/utils/err'

/**
 * An «анкета» filled by a link. Open form: no login. Closed form: the link asks to sign in first.
 * Sections go one by one; an answer may send the person to another section (the server checks the same path).
 */
type Step = 'loading' | 'missing' | 'login' | 'off' | 'fill' | 'done'
const { t } = useI18n()
const route = useRoute()
const auth = useAuthStore()
const token = computed(() => String(route.params.token ?? ''))

const step = ref<Step>('loading')
const form = ref<PublicForm | null>(null)
const title = ref('')
const viaLogin = ref(false)
const answers = reactive<FormAnswers>({})
const path = ref<string[]>([])
const errors = reactive<Record<string, string>>({})
const formErr = ref<string | null>(null)
const busy = ref(false)
const thanks = ref<string | null>(null)

onMounted(async () => {
  try {
    let f = await formsApi.publicGet(token.value)
    title.value = f.title
    if (f.closed) {
      if (!auth.isAuthenticated) return (step.value = 'login')
      f = await formsApi.myGet(token.value)
      viaLogin.value = true
    }
    if (!f.active) return (step.value = 'off')
    form.value = f
    document.title = `${f.title} · One English`
    path.value = f.sections[0] ? [f.sections[0].id] : []
    step.value = 'fill'
  } catch {
    step.value = 'missing'
  }
})

const section = computed<FormSection | null>(() => form.value?.sections.find((s) => s.id === path.value[path.value.length - 1]) ?? null)
function nextOf(s: FormSection): string | null {
  let nxt = s.next ?? null
  for (const q of s.questions) {
    const a = answers[q.id]
    if (q.kind === 'single' && typeof a === 'number' && q.options?.[a]?.goto) nxt = q.options[a].goto!
  }
  if (nxt) return nxt
  const all = form.value?.sections ?? []
  return all[all.findIndex((x) => x.id === s.id) + 1]?.id ?? null
}
const isLast = computed(() => !!section.value && !nextOf(section.value))

const branchId = computed(() => {
  const q = form.value?.sections.flatMap((s) => s.questions).find((x) => x.kind === 'branch')
  return q && typeof answers[q.id] === 'number' ? (answers[q.id] as number) : null
})
function selectOpts(q: FormQuestion) {
  const first = { value: -1, label: t('nv.fm.pick') }
  if (q.kind === 'branch') return [first, ...(form.value?.branches ?? []).map((b) => ({ value: b.id, label: b.name }))]
  if (q.kind === 'teacher') return [first, ...(form.value?.teachers ?? []).filter((x) => !branchId.value || !x.branch_ids.length || x.branch_ids.includes(branchId.value)).map((x) => ({ value: x.id, label: x.name }))]
  return [first, ...(q.options ?? []).map((o, i) => ({ value: i, label: o.text }))]
}
const sel = (q: FormQuestion) => (typeof answers[q.id] === 'number' ? (answers[q.id] as number) : -1)
function setSel(q: FormQuestion, v: number) {
  answers[q.id] = v < 0 ? null : v
  delete errors[q.id]
  if (q.kind === 'branch') for (const x of form.value?.sections.flatMap((s) => s.questions) ?? []) if (x.kind === 'teacher') answers[x.id] = null
}
const str = (q: FormQuestion) => (typeof answers[q.id] === 'string' ? (answers[q.id] as string) : '')
function setStr(q: FormQuestion, v: string) {
  answers[q.id] = v
  delete errors[q.id]
}
const multi = (q: FormQuestion) => {
  const a = answers[q.id]
  return a && typeof a === 'object' ? a : { picked: [] as number[], other: null as string | null }
}
function toggle(q: FormQuestion, i: number) {
  const m = multi(q)
  answers[q.id] = { ...m, picked: m.picked.includes(i) ? m.picked.filter((x) => x !== i) : [...m.picked, i] }
  delete errors[q.id]
}
function setOther(q: FormQuestion, v: string) {
  answers[q.id] = { ...multi(q), other: v || null }
  delete errors[q.id]
}
const scaleNums = (q: FormQuestion) => Array.from({ length: (q.max ?? 10) - (q.min ?? 1) + 1 }, (_, i) => (q.min ?? 1) + i)

function filled(q: FormQuestion): boolean {
  const a = answers[q.id]
  if (a === null || a === undefined) return false
  if (typeof a === 'string') return a.trim().length > 0
  if (typeof a === 'object') return a.picked.length > 0 || !!a.other?.trim()
  return true
}
function check(): boolean {
  Object.keys(errors).forEach((k) => delete errors[k])
  for (const q of section.value?.questions ?? []) if (q.required && !filled(q)) errors[q.id] = t('nv.fm.required')
  const first = Object.keys(errors)[0]
  if (first) document.getElementById(`fq-${first}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  return !first
}
const top = () => document.querySelector('.pt-main')?.scrollIntoView({ block: 'start' })
function next() {
  if (!section.value || !check()) return
  const n = nextOf(section.value)
  if (n) {
    path.value = [...path.value, n]
    top()
  }
}
function back() {
  path.value = path.value.slice(0, -1)
  top()
}
async function send() {
  if (!check()) return
  busy.value = true
  formErr.value = null
  try {
    const r = await (viaLogin.value ? formsApi.mySend : formsApi.publicSend)(token.value, { ...answers })
    thanks.value = r.thanks
    step.value = 'done'
    top()
  } catch (e) {
    formErr.value = apiErr(e) ?? t('errors.generic')
  } finally {
    busy.value = false
  }
}
const pct = computed(() => {
  const all = form.value?.sections ?? []
  const i = all.findIndex((s) => s.id === section.value?.id)
  return all.length ? Math.round(((i + 1) / all.length) * 100) : 0
})
</script>

<template>
  <div class="pt">
    <header class="pt-top"><BrandLogo :size="34" :tagline="false" /><span class="sp" /></header>
    <main class="pt-main">
      <section v-if="step === 'loading'" class="card pt-card"><UiSkeleton :lines="6" /></section>

      <section v-else-if="step === 'missing' || step === 'off'" class="card pt-card pt-center">
        <UiIcon name="file" :size="40" class="pt-big-ico" />
        <h1>{{ step === 'off' ? t('nv.fm.off') : t('nv.fm.missing') }}</h1>
      </section>

      <section v-else-if="step === 'login'" class="card pt-card pt-center">
        <UiIcon name="lock" :size="40" class="pt-big-ico" />
        <h1>{{ title }}</h1>
        <p class="muted">{{ t('nv.fm.needLogin') }}</p>
        <UiButton variant="primary" :to="{ name: 'login', query: { as: 'client', redirect: route.fullPath } }">{{ t('nv.fm.login') }}</UiButton>
      </section>

      <section v-else-if="step === 'fill' && form && section" class="card pt-card">
        <template v-if="path.length === 1">
          <h1>{{ form.title }}</h1>
          <p v-if="form.description" class="muted pt-intro">{{ form.description }}</p>
        </template>
        <template v-else>
          <h1>{{ section.title }}</h1>
          <p v-if="section.text" class="muted pt-intro">{{ section.text }}</p>
        </template>
        <div class="bar-track" role="progressbar" :aria-valuenow="pct" aria-valuemin="0" aria-valuemax="100"><i :style="{ width: `${pct}%` }" /></div>

        <fieldset v-for="q in section.questions" :id="`fq-${q.id}`" :key="q.id" class="pt-q fq" :class="{ bad: errors[q.id] }">
          <legend>{{ q.text }}<span v-if="q.required" class="fq-req" aria-hidden="true"> *</span></legend>
          <UiInput v-if="q.kind === 'short'" :model-value="str(q)" :aria-label="q.text" :maxlength="200" autocomplete="name" @update:model-value="setStr(q, String($event))" />
          <UiPhoneInput v-else-if="q.kind === 'phone'" :model-value="str(q)" :label="''" :aria-label="q.text" @update:model-value="setStr(q, String($event))" />
          <UiTextarea v-else-if="q.kind === 'para'" :model-value="str(q)" :aria-label="q.text" :rows="3" :maxlength="2000" @update:model-value="setStr(q, String($event))" />
          <UiSelect v-else-if="q.kind === 'select' || q.kind === 'branch' || q.kind === 'teacher'" :model-value="sel(q)" :options="selectOpts(q)" :label="q.text" block @update:model-value="setSel(q, Number($event))" />
          <div v-else-if="q.kind === 'scale'" class="fq-scale">
            <div class="fq-nums">
              <button v-for="n in scaleNums(q)" :key="n" type="button" :class="{ on: answers[q.id] === n }" :aria-pressed="answers[q.id] === n" @click="setSel(q, n)">{{ n }}</button>
            </div>
            <div class="fq-ends"><span>{{ q.min }}: {{ q.low }}</span><span>{{ q.max }}: {{ q.high }}</span></div>
          </div>
          <div v-else class="pt-opts">
            <label v-for="(o, i) in q.options" :key="i" class="pt-opt" :class="{ on: q.kind === 'multi' ? multi(q).picked.includes(i) : answers[q.id] === i }">
              <input :type="q.kind === 'multi' ? 'checkbox' : 'radio'" :name="q.id" :checked="q.kind === 'multi' ? multi(q).picked.includes(i) : answers[q.id] === i" @change="q.kind === 'multi' ? toggle(q, i) : setSel(q, i)" />
              <span class="pt-mark" :class="q.kind" aria-hidden="true" />
              <span class="pt-otext">{{ o.text }}</span>
            </label>
            <UiInput v-if="q.other" :model-value="multi(q).other ?? ''" :placeholder="t('nv.fm.other')" :aria-label="t('nv.fm.other')" :maxlength="300" @update:model-value="setOther(q, String($event))" />
          </div>
          <p v-if="errors[q.id]" class="form-err m0" role="alert">{{ errors[q.id] }}</p>
        </fieldset>

        <p v-if="formErr" class="form-err" role="alert">{{ formErr }}</p>
        <div class="pt-nav">
          <UiButton v-if="path.length > 1" variant="ghost" :disabled="busy" @click="back">{{ t('common.back') }}</UiButton>
          <span class="sp" />
          <UiButton v-if="!isLast" variant="primary" size="lg" icon-end="arrow" @click="next">{{ t('nv.gt.next') }}</UiButton>
          <UiButton v-else variant="primary" size="lg" icon="ok" :loading="busy" @click="send">{{ t('nv.fm.send') }}</UiButton>
        </div>
      </section>

      <section v-else-if="step === 'done'" class="card pt-card pt-center">
        <span class="pt-done-ico"><UiIcon name="ok" :size="40" /></span>
        <h1>{{ t('nv.fm.sent') }}</h1>
        <p v-if="thanks" class="muted">{{ thanks }}</p>
      </section>
    </main>
    <footer class="pt-foot">{{ t('app.footer') }}</footer>
  </div>
</template>

<style scoped>
.fq { padding-top: 6px }
.fq.bad legend { color: var(--red-ink) }
.fq-req { color: var(--red-ink) }
.fq-nums { display: grid; grid-template-columns: repeat(auto-fit, minmax(40px, 1fr)); gap: 6px }
.fq-nums button { min-height: 44px; border-radius: 10px; border: 1px solid var(--line); background: var(--surface); font: inherit; font-weight: 600; color: var(--ink); cursor: pointer }
.fq-nums button:hover { border-color: var(--navy-600) }
.fq-nums button.on { background: var(--btn-navy); border-color: var(--btn-navy); color: var(--on-accent) }
.fq-ends { display: flex; justify-content: space-between; gap: 12px; margin-top: 6px; font-size: 12.5px; color: var(--muted) }
</style>
