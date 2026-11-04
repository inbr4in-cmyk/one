<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiDrawer, UiField, UiIcon, UiInput, UiSelect, UiSkeleton, UiSwitch, UiTextarea } from '@/components/ui'
import { testsApi, type Question, type QuestionKind, type ScaleRow, type Test, type TestIn, type TestKind } from '@/api/assessment'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import { apiErr } from '@/utils/err'

/**
 * Test builder: settings (kind, title, scale, publish) and the question list.
 * `test` null = create; after the first save the drawer switches to editing so questions can be added.
 */
const props = defineProps<{ test: Test | null; canEdit: boolean }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ saved: [test: Test] }>()

const { t } = useI18n()
const refs = useRefsStore()
const toast = useToastStore()

const current = ref<Test | null>(null)
const form = reactive({ kind: 'placement' as TestKind, title: '', level_id: 0, max_score: '150', pass_score: '', time_limit_min: '', is_published: false })
const scale = ref<{ min: string; level_id: number }[]>([])
const error = ref<string | null>(null)
const busy = ref(false)

const questions = ref<Question[] | null>(null)
const qOpen = ref(false)
const qEditing = ref<Question | null>(null)
const qForm = reactive({ kind: 'single' as QuestionKind, text: '', options: ['', ''] as string[], correct: [] as number[], points: '1' })
const qError = ref<string | null>(null)
const qBusy = ref(false)

const kinds = computed(() => (['placement', 'final', 'training'] as const).map((k) => ({ value: k, label: t(`tests.kind.${k}`) })))
const qKinds = computed(() => (['single', 'multi', 'text'] as const).map((k) => ({ value: k, label: t(`tests.q.kind.${k}`) })))
const levelOpts = computed(() => [{ value: 0, label: t('tests.noLevel') }, ...refs.levels.map((l) => ({ value: l.id, label: l.name }))])

watch(open, async (v) => {
  if (!v) return
  void refs.load()
  current.value = props.test
  error.value = null
  qOpen.value = false
  const x = props.test
  Object.assign(form, {
    kind: x?.kind ?? 'placement',
    title: x?.title ?? '',
    level_id: x?.level_id ?? 0,
    max_score: String(x?.max_score ?? 150),
    pass_score: x?.pass_score != null ? String(x.pass_score) : '',
    time_limit_min: x?.time_limit_min != null ? String(x.time_limit_min) : '',
    is_published: x?.is_published ?? false,
  })
  const rows = Array.isArray(x?.scale) ? (x.scale as ScaleRow[]) : []
  scale.value = rows.map((r) => ({ min: String(r.min ?? 0), level_id: r.level_id ?? 0 }))
  questions.value = null
  if (x) await loadQuestions()
  else questions.value = []
}, { immediate: true })

async function loadQuestions() {
  if (!current.value) return
  questions.value = props.canEdit ? await testsApi.questions(current.value.id).catch(() => []) : []
}

const num = (v: string) => (v.trim() === '' ? null : Number(v))

async function saveTest() {
  error.value = form.title.trim().length < 2 ? t('tests.titleRequired') : null
  if (error.value) return
  const body: TestIn = {
    kind: form.kind,
    title: form.title.trim(),
    level_id: form.level_id || null,
    max_score: num(form.max_score) ?? 150,
    pass_score: num(form.pass_score),
    time_limit_min: num(form.time_limit_min),
    is_published: form.is_published,
    scale: form.kind === 'placement'
      ? scale.value.filter((r) => r.level_id).map((r) => ({ min: Number(r.min) || 0, level_id: r.level_id })).sort((a, b) => a.min - b.min)
      : [],
  }
  busy.value = true
  try {
    const saved = current.value ? await testsApi.update(current.value.id, body) : await testsApi.create(body)
    toast.ok(current.value ? t('tests.saved') : t('tests.created'))
    saved.questions = questions.value?.length ?? saved.questions
    current.value = saved
    emit('saved', saved)
  } catch (e) {
    error.value = apiErr(e) ?? t('errors.generic')
  } finally {
    busy.value = false
  }
}

/* ---------- questions ---------- */
function newQuestion() {
  qEditing.value = null
  Object.assign(qForm, { kind: 'single', text: '', options: ['', '', '', ''], correct: [], points: '1' })
  qError.value = null
  qOpen.value = true
}
function editQuestion(q: Question) {
  qEditing.value = q
  Object.assign(qForm, { kind: q.kind, text: q.text, options: q.options.length ? [...q.options] : ['', ''], correct: [...q.correct], points: String(q.points) })
  qError.value = null
  qOpen.value = true
}
function toggleCorrect(i: number) {
  if (qForm.kind === 'single') qForm.correct = [i]
  else qForm.correct = qForm.correct.includes(i) ? qForm.correct.filter((x) => x !== i) : [...qForm.correct, i].sort((a, b) => a - b)
}
function removeOption(i: number) {
  qForm.options.splice(i, 1)
  qForm.correct = qForm.correct.filter((x) => x !== i).map((x) => (x > i ? x - 1 : x))
}
watch(() => qForm.kind, (k) => {
  if (k === 'single' && qForm.correct.length > 1) qForm.correct = qForm.correct.slice(0, 1)
})

async function saveQuestion() {
  if (!current.value) return
  const text = qForm.text.trim()
  // Empty options are dropped; correct indexes follow the options that stay.
  const keep = qForm.options.map((o, i) => ({ o: o.trim(), i })).filter((x) => x.o)
  const options = qForm.kind === 'text' ? [] : keep.map((x) => x.o)
  const correct = qForm.kind === 'text' ? [] : keep.map((x, j) => (qForm.correct.includes(x.i) ? j : -1)).filter((j) => j >= 0)
  qError.value = !text ? t('tests.q.needText') : qForm.kind !== 'text' && (options.length < 2 || !correct.length) ? t('tests.q.needOptions') : null
  if (qError.value) return
  const body = {
    order: qEditing.value?.order ?? (questions.value?.length ?? 0) + 1,
    kind: qForm.kind,
    text,
    options,
    correct,
    points: Math.max(0, Math.min(150, Number(qForm.points) || 0)),
  }
  qBusy.value = true
  try {
    if (qEditing.value) await testsApi.updateQuestion(qEditing.value.id, body)
    else await testsApi.addQuestion(current.value.id, body)
    toast.ok(t('tests.q.saved'))
    qOpen.value = false
    await loadQuestions()
    if (current.value) emit('saved', { ...current.value, questions: questions.value?.length ?? 0 })
  } catch (e) {
    qError.value = apiErr(e) ?? t('errors.generic')
  } finally {
    qBusy.value = false
  }
}

async function archiveQuestion(q: Question) {
  if (!window.confirm(`${t('tests.q.archive')}?`)) return
  try {
    await testsApi.archiveQuestion(q.id)
    toast.ok(t('tests.q.archived'))
    await loadQuestions()
    if (current.value) emit('saved', { ...current.value, questions: questions.value?.length ?? 0 })
  } catch {
    /* toast shown by the client */
  }
}
</script>

<template>
  <UiDrawer v-model:open="open" :title="current ? current.title : t('tests.newTitle')">
    <form id="test-form" class="stack" @submit.prevent="saveTest">
      <UiField :label="t('tests.kindLabel')">
        <UiSelect v-model="form.kind" :options="kinds" :label="t('tests.kindLabel')" block :disabled="!canEdit" />
      </UiField>
      <UiInput v-model="form.title" :label="t('tests.title')" :placeholder="t('tests.titlePh')" :maxlength="255" :disabled="!canEdit" />
      <div class="form-2">
        <UiInput v-model="form.max_score" type="number" inputmode="numeric" :min="1" :max="1000" :label="t('tests.maxScore')" :disabled="!canEdit" />
        <UiInput v-model="form.time_limit_min" type="number" inputmode="numeric" :min="1" :max="300" :label="t('tests.timeLimit')" :hint="t('tests.timeLimitHint')" :disabled="!canEdit" />
      </div>
      <div v-if="form.kind !== 'placement'" class="form-2">
        <UiField :label="t('tests.level')"><UiSelect v-model="form.level_id" :options="levelOpts" :label="t('tests.level')" block :disabled="!canEdit" /></UiField>
        <UiInput v-model="form.pass_score" type="number" inputmode="numeric" :min="0" :label="t('tests.passScore')" :disabled="!canEdit" />
      </div>
      <UiField v-else :label="t('tests.scale')" :hint="t('tests.scaleHint')">
        <div class="tst-scale">
          <div v-for="(r, i) in scale" :key="i" class="tst-scale-row">
            <input v-model="r.min" class="inp mini" type="number" min="0" inputmode="numeric" :aria-label="t('tests.scaleFrom')" :placeholder="t('tests.scaleFrom')" :disabled="!canEdit" />
            <UiSelect v-model="r.level_id" :options="levelOpts" :label="t('tests.level')" block :disabled="!canEdit" />
            <button v-if="canEdit" type="button" class="dlg-x" :aria-label="t('common.remove')" @click="scale.splice(i, 1)"><UiIcon name="x" :size="16" /></button>
          </div>
          <UiButton v-if="canEdit" size="sm" variant="ghost" icon="plus" style="justify-self: start" @click="scale.push({ min: '', level_id: 0 })">{{ t('tests.scaleAdd') }}</UiButton>
        </div>
      </UiField>
      <div class="set-row" style="border: 0; padding: 0">
        <div class="grow"><b>{{ t('tests.published') }}</b><span v-if="form.kind === 'placement'">{{ t('tests.publishedHint') }}</span></div>
        <UiSwitch v-model="form.is_published" :label="t('tests.published')" :disabled="!canEdit" />
      </div>
      <p v-if="error" class="form-err" role="alert">{{ error }}</p>
      <UiButton v-if="canEdit" type="submit" variant="navy" :loading="busy" style="justify-self: start">{{ current ? t('tests.save') : t('tests.newTitle') }}</UiButton>
    </form>

    <template v-if="current">
      <hr class="sep" style="margin: 18px 0 14px" />
      <div class="sub-h"><b>{{ t('tests.questions') }}</b><span class="muted">· {{ questions?.length ?? '…' }}</span><span class="sp" />
        <UiButton v-if="canEdit && !qOpen" size="sm" icon="plus" @click="newQuestion">{{ t('tests.q.add') }}</UiButton>
      </div>

      <form v-if="qOpen" class="g-box" style="margin-top: 12px" @submit.prevent="saveQuestion">
        <b>{{ qEditing ? t('tests.q.editTitle') : t('tests.q.newTitle') }}</b>
        <UiField :label="t('tests.q.kindLabel')"><UiSelect v-model="qForm.kind" :options="qKinds" :label="t('tests.q.kindLabel')" block /></UiField>
        <UiTextarea v-model="qForm.text" :label="t('tests.q.text')" :placeholder="t('tests.q.textPh')" :rows="2" :maxlength="2000" />
        <UiField v-if="qForm.kind !== 'text'" :label="t('tests.q.options')">
          <div class="stack" style="gap: 8px">
            <div v-for="(_, i) in qForm.options" :key="i" class="tst-opt">
              <button type="button" class="tgl sm" :aria-pressed="qForm.correct.includes(i)" :title="t('tests.q.correct')" :aria-label="`${t('tests.q.correct')}: ${i + 1}`" @click="toggleCorrect(i)"><UiIcon name="ok" :size="16" /></button>
              <input v-model="qForm.options[i]" class="inp mini" :placeholder="t('tests.q.optionPh', { n: i + 1 })" :aria-label="t('tests.q.optionPh', { n: i + 1 })" maxlength="500" />
              <button v-if="qForm.options.length > 2" type="button" class="dlg-x" :aria-label="t('tests.q.removeOption', { n: i + 1 })" @click="removeOption(i)"><UiIcon name="x" :size="16" /></button>
            </div>
            <UiButton v-if="qForm.options.length < 8" size="sm" variant="ghost" icon="plus" style="justify-self: start" @click="qForm.options.push('')">{{ t('tests.q.addOption') }}</UiButton>
          </div>
        </UiField>
        <p v-else class="form-note">{{ t('tests.q.textAnswer') }}</p>
        <UiInput v-model="qForm.points" type="number" inputmode="numeric" :min="0" :max="150" :label="t('tests.q.points')" style="max-width: 140px" />
        <p v-if="qError" class="form-err" role="alert">{{ qError }}</p>
        <div class="row-actions">
          <UiButton type="submit" variant="navy" size="sm" :loading="qBusy">{{ t('common.save') }}</UiButton>
          <UiButton size="sm" @click="qOpen = false">{{ t('common.cancel') }}</UiButton>
        </div>
      </form>

      <div v-if="!questions" style="margin-top: 12px"><UiSkeleton :lines="4" /></div>
      <p v-else-if="!questions.length && !qOpen" class="muted" style="margin: 12px 0 0">{{ t('tests.noQuestions') }}</p>
      <div v-else class="tst-qs" style="margin-top: 12px">
        <div v-for="(q, i) in questions" :key="q.id" class="tst-q">
          <span class="n">{{ i + 1 }}</span>
          <div class="grow">
            <b>{{ q.text }}</b>
            <span class="muted" style="font-size: 12px">{{ t(`tests.q.kind.${q.kind}`) }} · {{ t('tests.q.points') }}: {{ q.points }}</span>
            <ol v-if="q.options.length"><li v-for="(o, j) in q.options" :key="j" :class="{ ok: q.correct.includes(j) }">{{ o }}</li></ol>
          </div>
          <template v-if="canEdit">
            <button type="button" class="dlg-x" :aria-label="`${t('common.edit')}: ${i + 1}`" :title="t('common.edit')" @click="editQuestion(q)"><UiIcon name="pencil" :size="16" /></button>
            <button type="button" class="dlg-x" :aria-label="`${t('tests.q.archive')}: ${i + 1}`" :title="t('tests.q.archive')" @click="archiveQuestion(q)"><UiIcon name="archive" :size="16" /></button>
          </template>
        </div>
      </div>
    </template>
  </UiDrawer>
</template>
