<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { toDataURL } from 'qrcode'
import { UiButton, UiCard, UiField, UiIcon, UiInput, UiSegmented, UiSelect, UiSkeleton } from '@/components/ui'
import { academicsApi } from '@/api/academics'
import { surveyApi, type SurveyLink, type SurveyQuestion, type SurveyResults } from '@/api/assessment'
import { useAuthStore } from '@/stores/auth'
import { useBranchStore } from '@/stores/branch'
import { useToastStore } from '@/stores/toast'
import { dayLabel, hm } from '@/utils/dates'
import { apiErr } from '@/utils/err'
import type { Locale } from '@/i18n'

/** Тесты → «Оценка урока»: pick a group, show the QR to the class; the owner and branch admins see the answers. */
const { t, locale } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const branch = useBranchStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)
const isAdmin = computed(() => auth.can('students.archive'))

const groups = ref<{ id: number; name: string }[] | null>(null)
const groupId = ref(0)
const link = ref<SurveyLink | null>(null)
const url = ref('')
const img = ref('')
const err = ref('')
const groupOpts = computed(() => [{ value: 0, label: t('nv.sv.pickGroup') }, ...(groups.value ?? []).map((g) => ({ value: g.id, label: g.name }))])

async function loadGroups() {
  groups.value = (await academicsApi.groups({ branch_id: branch.filterId }).catch(() => [])).map((g) => ({ id: g.id, name: g.name }))
}
watch(groupId, async (id) => {
  link.value = null
  url.value = img.value = err.value = ''
  if (!id) return
  try {
    const r = await surveyApi.open(id)
    link.value = r
    url.value = new URL(router.resolve(r.path).href, window.location.href).href
    img.value = await toDataURL(url.value, { margin: 1, width: 480, errorCorrectionLevel: 'M', color: { dark: '#012169', light: '#FFFFFF' } })
  } catch (e) {
    err.value = apiErr(e) ?? t('errors.generic')
  }
})
async function copy() {
  try {
    await navigator.clipboard.writeText(url.value)
    toast.ok(t('common.copied'))
  } catch {
    /* the link is on the screen */
  }
}

/* ---------- admins: questions and answers ---------- */
const questions = ref<SurveyQuestion[]>([])
const editing = ref(false)
const busy = ref(false)
const results = ref<SurveyResults | null>(null)
const openRow = ref<number | null>(null)
const kinds = computed(() => [{ value: 'stars', label: t('nv.sv.stars') }, { value: 'text', label: t('nv.sv.text') }])

async function loadAdmin() {
  if (!isAdmin.value) return
  questions.value = await surveyApi.questions().catch(() => [])
  results.value = await surveyApi.results({ branch_id: branch.filterId }).catch(() => null)
}
async function saveQuestions() {
  busy.value = true
  try {
    questions.value = await surveyApi.setQuestions(questions.value.map((q) => ({ text: q.text.trim(), kind: q.kind })))
    editing.value = false
    toast.ok(t('common.saved'))
  } catch (e) {
    toast.error(apiErr(e) ?? t('errors.generic'))
  } finally {
    busy.value = false
  }
}
onMounted(() => {
  loadGroups()
  loadAdmin()
})
watch(() => branch.filterId, () => {
  groupId.value = 0
  loadGroups()
  loadAdmin()
})
const stars = (v: number | null | undefined) => (v == null ? '—' : v.toFixed(1))
</script>

<template>
  <UiCard :title="t('nv.sv.title')" icon="star">
    <div class="qr-card">
      <div class="qr">
        <img v-if="img" :src="img" :alt="t('nv.sv.title')" />
        <UiIcon v-else name="qr" :size="40" class="muted" />
      </div>
      <div class="grow">
        <UiSkeleton v-if="!groups" :lines="2" />
        <UiField v-else :label="t('nv.sv.group')"><UiSelect v-model="groupId" :options="groupOpts" :label="t('nv.sv.group')" block /></UiField>
        <p v-if="err" class="form-err" role="alert">{{ err }}</p>
        <template v-if="link">
          <p class="m0"><b>{{ link.group }}</b> · {{ t('nv.sv.lessonAt', { when: link.lesson }) }} · {{ t('nv.sv.answersN', { n: link.answers }) }}</p>
          <div class="qr-link">{{ url }}</div>
          <div class="row-actions">
            <UiButton size="sm" icon="clip" @click="copy">{{ t('tests.qr.copy') }}</UiButton>
            <UiButton size="sm" variant="ghost" icon="globe" :href="url" target="_blank" rel="noopener">{{ t('tests.qr.open') }}</UiButton>
          </div>
        </template>
      </div>
    </div>

    <template v-if="isAdmin">
      <div class="sv-h"><b>{{ t('nv.sv.questions') }}</b><span class="sp" />
        <UiButton v-if="!editing" size="sm" variant="ghost" icon="edit" @click="editing = true">{{ t('common.edit') }}</UiButton></div>
      <ol v-if="!editing" class="sv-q"><li v-for="(q, i) in questions" :key="i">{{ q.text }} <span class="muted">· {{ q.kind === 'stars' ? t('nv.sv.stars') : t('nv.sv.text') }}</span></li></ol>
      <form v-else class="stack" @submit.prevent="saveQuestions">
        <div v-for="(q, i) in questions" :key="i" class="sv-edit">
          <UiInput v-model="q.text" :label="t('nv.sv.questionN', { n: i + 1 })" :maxlength="200" />
          <UiSegmented v-model="q.kind" :options="kinds" :label="t('nv.sv.kind')" size="sm" />
          <UiButton v-if="questions.length > 1" size="sm" variant="ghost" danger icon="delete" :aria-label="t('common.remove')" @click="questions.splice(i, 1)" />
        </div>
        <div class="row-actions">
          <UiButton v-if="questions.length < 6" size="sm" icon="plus" @click="questions.push({ text: '', kind: 'stars' })">{{ t('nv.sv.addQuestion') }}</UiButton>
          <UiButton type="submit" size="sm" variant="navy" :loading="busy">{{ t('common.save') }}</UiButton>
        </div>
      </form>

      <template v-if="results?.teachers.length">
        <div class="sv-h"><b>{{ t('nv.sv.byTeacher') }}</b></div>
        <div class="scroll-x"><table class="tbl">
          <thead><tr><th scope="col">{{ t('nv.sv.teacher') }}</th><th scope="col" class="r">{{ t('nv.sv.lessons') }}</th><th scope="col" class="r">{{ t('nv.sv.answers') }}</th><th scope="col" class="r">{{ t('nv.sv.avg') }}</th></tr></thead>
          <tbody><tr v-for="p in results.teachers" :key="p.teacher_id"><td>{{ p.teacher }}</td><td class="r num">{{ p.lessons }}</td><td class="r num">{{ p.answers }}</td><td class="r num"><b>{{ stars(p.avg) }}</b></td></tr></tbody>
        </table></div>
      </template>
      <template v-if="results?.lessons.length">
        <div class="sv-h"><b>{{ t('nv.sv.byLesson') }}</b></div>
        <div class="scroll-x"><table class="tbl hover">
          <thead><tr><th scope="col">{{ t('nv.sv.lesson') }}</th><th scope="col">{{ t('nv.sv.group') }}</th><th scope="col">{{ t('nv.sv.teacher') }}</th><th scope="col" class="r">{{ t('nv.sv.answers') }}</th><th scope="col" class="r">{{ t('nv.sv.avg') }}</th></tr></thead>
          <tbody>
            <template v-for="r in results.lessons" :key="r.survey_id">
              <tr style="cursor: pointer" @click="openRow = openRow === r.survey_id ? null : r.survey_id">
                <td class="num">{{ dayLabel(r.at, loc, { day: 'numeric', month: 'short' }) }}, {{ hm(r.at, loc) }}</td><td>{{ r.group ?? '—' }}</td><td>{{ r.teacher ?? '—' }}</td>
                <td class="r num">{{ r.answers }}</td><td class="r num"><b>{{ stars(r.avg) }}</b></td>
              </tr>
              <tr v-if="openRow === r.survey_id"><td colspan="5">
                <div v-for="(q, i) in r.questions" :key="i" class="sv-res">
                  <b>{{ q.text }}</b>
                  <span v-if="q.kind === 'stars'" class="num">{{ stars(q.avg) }} · {{ t('nv.sv.answersN', { n: q.count ?? 0 }) }}</span>
                  <ul v-else-if="q.comments?.length"><li v-for="(c, j) in q.comments" :key="j">{{ c }}</li></ul>
                  <span v-else class="muted">—</span>
                </div>
              </td></tr>
            </template>
          </tbody>
        </table></div>
      </template>
      <p v-else-if="results" class="muted" style="margin: 12px 0 0">{{ t('nv.sv.noAnswers') }}</p>
    </template>
  </UiCard>
</template>
