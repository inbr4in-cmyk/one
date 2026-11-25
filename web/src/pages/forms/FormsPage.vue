<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import LessonSurveyCard from '@/components/tests/LessonSurveyCard.vue'
import { UiButton, UiCard, UiChip, UiEmptyState, UiIcon, UiModal, UiSegmented, UiSkeleton, UiSwitch, UiTextarea } from '@/components/ui'
import { formsApi, type FormInfo, type FormRow, type FormSummary } from '@/api/forms'
import { useAuthStore } from '@/stores/auth'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import { dmy, hm } from '@/utils/dates'
import { formatPhone } from '@/utils/phone'
import type { Locale } from '@/i18n'

/** «Оценки и анкеты»: the lesson rating by QR and the school's forms with every sent answer kept like an application. */
const { t, locale } = useI18n()
const loc = computed(() => locale.value as Locale)
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const refs = useRefsStore()
const toast = useToastStore()

/** «Оценка урока» by QR is hidden for now at the owner's request (25.11.2026); nothing is deleted, old links and answers stay */
const SHOW_LESSON_SURVEY = false
const canSee = computed(() => auth.can('students.archive'))
const canSet = computed(() => auth.user?.permissions?.['students.archive'] === 'network')
const forms = ref<FormInfo[] | null>(null)
type View = 'new' | 'done' | 'all' | 'summary'
const view = reactive<Record<number, View>>({})
const rows = reactive<Record<number, FormRow[] | null>>({})
const sums = reactive<Record<number, FormSummary | null>>({})
const views = computed(() => [
  { value: 'new' as const, label: t('nv.fm.vNew') },
  { value: 'done' as const, label: t('nv.fm.vDone') },
  { value: 'all' as const, label: t('nv.fm.vAll') },
  { value: 'summary' as const, label: t('nv.fm.vSummary') },
])

async function load() {
  if (!canSee.value) return (forms.value = [])
  forms.value = await formsApi.list().catch(() => [])
  for (const f of forms.value) {
    view[f.id] ??= 'new'
    loadRows(f.id)
  }
}
async function loadRows(id: number) {
  const v = view[id]
  if (v === 'summary') {
    sums[id] = null
    sums[id] = await formsApi.summary(id).catch(() => null)
    return
  }
  rows[id] = null
  rows[id] = await formsApi.responses(id, v === 'all' ? {} : { status: v }).catch(() => [])
}
function setView(id: number, v: View) {
  view[id] = v
  loadRows(id)
}
onMounted(async () => {
  await Promise.all([load(), refs.load()])
  const r = Number(route.query.r)
  if (r && canSee.value) open(r)
})

const link = (f: FormInfo) => new URL(router.resolve(f.path).href, window.location.href).href
async function copy(f: FormInfo) {
  try {
    await navigator.clipboard.writeText(link(f))
    toast.ok(t('common.copied'))
  } catch {
    toast.error(t('errors.generic'))
  }
}
async function patch(f: FormInfo, body: { is_open?: boolean; is_active?: boolean }) {
  const r = await formsApi.patch(f.id, body).catch(() => null)
  if (r && forms.value) forms.value = forms.value.map((x) => (x.id === f.id ? { ...x, is_open: r.is_open, is_active: r.is_active } : x))
}
const access = computed(() => [{ value: 'open' as const, label: t('nv.fm.open') }, { value: 'closed' as const, label: t('nv.fm.closed') }])

/* ---------- one answer ---------- */
const cur = ref<FormRow | null>(null)
const modal = ref(false)
const note = ref('')
const busy = ref(false)
async function open(id: number) {
  cur.value = null
  modal.value = true
  cur.value = await formsApi.response(id).catch(() => null)
  note.value = cur.value?.note ?? ''
  if (!cur.value) modal.value = false
}
watch(modal, (v) => !v && route.query.r && router.replace({ query: { ...route.query, r: undefined } }))
async function setDone(done: boolean) {
  if (!cur.value) return
  busy.value = true
  try {
    cur.value = await formsApi.done(cur.value.id, { done, note: note.value.trim() || null })
    toast.ok(t('common.saved'))
    modal.value = false
    await load()
  } catch {
    /* toast shown by the client */
  } finally {
    busy.value = false
  }
}
const when = (iso: string) => `${dmy(iso, loc.value)} ${hm(iso, loc.value)}`
const branchName = (id: string) => (id === '0' ? '—' : refs.branchName(Number(id)) || id)
const branchKeys = (s: FormSummary) => [...new Set(s.questions.flatMap((q) => (q.kind === 'choice' ? q.options.flatMap((o) => Object.keys(o.by_branch)) : [])))].sort()
</script>

<template>
  <div class="grid">
    <template v-if="canSee">
      <div v-if="!forms" class="card card-pad"><UiSkeleton :lines="5" /></div>
      <UiCard v-for="f in forms ?? []" :key="f.id" :title="f.title" icon="file">
        <template #actions>
          <UiChip v-if="f.new" tone="red">{{ t('nv.fm.newN', { n: f.new }) }}</UiChip>
        </template>
        <div class="fm-set">
          <UiSegmented v-if="canSet" :model-value="f.is_open ? 'open' : 'closed'" :options="access" :label="t('nv.fm.access')" size="sm" @update:model-value="patch(f, { is_open: $event === 'open' })" />
          <UiChip v-else :tone="f.is_open ? 'ok' : 'info'">{{ f.is_open ? t('nv.fm.open') : t('nv.fm.closed') }}</UiChip>
          <label v-if="canSet" class="fm-sw"><UiSwitch :model-value="f.is_active" :label="t('nv.fm.active')" @update:model-value="patch(f, { is_active: $event })" />{{ t('nv.fm.active') }}</label>
          <span class="muted">{{ t('nv.fm.meta', { s: f.sections, q: f.questions, n: f.total }) }}</span>
        </div>
        <div class="row-actions fm-link">
          <span class="qr-link grow">{{ link(f) }}</span>
          <UiButton size="sm" icon="clip" @click="copy(f)">{{ t('tests.qr.copy') }}</UiButton>
          <UiButton size="sm" variant="ghost" icon="globe" :href="link(f)" target="_blank" rel="noopener">{{ t('tests.qr.open') }}</UiButton>
        </div>

        <div class="fm-tabs"><UiSegmented :model-value="view[f.id] ?? 'new'" :options="views" :label="t('nv.fm.answers')" size="sm" @update:model-value="setView(f.id, $event)" /></div>

        <template v-if="view[f.id] === 'summary'">
          <UiSkeleton v-if="!sums[f.id]" :lines="4" />
          <UiEmptyState v-else-if="!sums[f.id]!.count" icon="file" :title="t('nv.fm.none')" />
          <div v-else class="fm-sum">
            <p class="m0 muted">{{ t('nv.fm.sumPeriod', { a: dmy(sums[f.id]!.date_from, loc), b: dmy(sums[f.id]!.date_to, loc), n: sums[f.id]!.count }) }}</p>
            <div v-for="q in sums[f.id]!.questions" :key="q.id" class="fm-sq">
              <b>{{ q.text }}</b>
              <span v-if="q.kind === 'scale'" class="num">{{ q.avg ?? '—' }} <small class="muted">· {{ t('nv.fm.answersN', { n: q.count }) }}</small></span>
              <table v-else class="tbl fm-st">
                <thead><tr><th /><th>{{ t('nv.fm.total') }}</th><th v-for="b in branchKeys(sums[f.id]!)" :key="b">{{ branchName(b) }}</th></tr></thead>
                <tbody><tr v-for="o in q.options" :key="o.text"><td>{{ o.text }}</td><td class="num"><b>{{ o.total }}</b></td><td v-for="b in branchKeys(sums[f.id]!)" :key="b" class="num">{{ o.by_branch[b] ?? 0 }}</td></tr></tbody>
              </table>
            </div>
          </div>
        </template>
        <template v-else>
          <UiSkeleton v-if="!rows[f.id]" :lines="3" />
          <UiEmptyState v-else-if="!rows[f.id]!.length" icon="file" :title="t('nv.fm.none')" />
          <div v-else class="fm-list">
            <button v-for="r in rows[f.id]" :key="r.id" type="button" class="list-row pick" @click="open(r.id)">
              <div class="grow">
                <b>{{ r.name ?? '—' }}<small v-if="r.phone" class="muted num"> · {{ formatPhone(r.phone) }}</small></b>
                <span>{{ [r.kind, r.branch, r.teacher].filter(Boolean).join(' · ') }} · {{ when(r.at) }}</span>
                <span v-if="r.flags.length && r.status === 'new'" class="fm-flag"><UiIcon name="alert" :size="14" />{{ t('nv.fm.callToday') }}: {{ r.flags.join('; ') }}</span>
              </div>
              <UiChip small :tone="r.status === 'done' ? 'ok' : r.flags.length ? 'red' : 'info'">{{ t(`nv.fm.st.${r.status}`) }}</UiChip>
              <UiIcon name="arrow" :size="16" class="muted" />
            </button>
          </div>
        </template>
      </UiCard>
    </template>
    <LessonSurveyCard v-if="SHOW_LESSON_SURVEY" />
  </div>

  <UiModal v-model:open="modal" :title="cur?.name ?? t('nv.fm.answer')">
    <UiSkeleton v-if="!cur" :lines="6" />
    <div v-else class="stack">
      <p class="m0 muted">{{ [cur.phone ? formatPhone(cur.phone) : null, cur.branch, cur.teacher, when(cur.at)].filter(Boolean).join(' · ') }}</p>
      <div v-if="cur.flags.length" class="alert red" style="margin: 0"><UiIcon name="alert" :size="18" class="ico" /><div class="grow"><b>{{ t('nv.fm.callToday') }}</b><span>{{ cur.flags.join('; ') }}</span></div></div>
      <div v-for="s in cur.sections" :key="s.title" class="fm-sec">
        <h3>{{ s.title }}</h3>
        <dl><template v-for="(it, i) in s.items" :key="i"><dt>{{ it.text }}</dt><dd :class="{ redc: it.low }">{{ it.value }}</dd></template></dl>
      </div>
      <UiTextarea v-model="note" :placeholder="t('nv.fm.note')" :aria-label="t('nv.fm.note')" :rows="2" :maxlength="1000" />
    </div>
    <template #footer="{ close }">
      <UiButton variant="ghost" @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton v-if="cur?.status === 'done'" :loading="busy" @click="setDone(false)">{{ t('nv.fm.reopen') }}</UiButton>
      <UiButton v-if="cur" variant="primary" icon="ok" :loading="busy" @click="setDone(true)">{{ cur.status === 'done' ? t('common.save') : t('nv.fm.markDone') }}</UiButton>
    </template>
  </UiModal>
</template>

<style scoped>
.fm-set { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; font-size: 13.5px }
.fm-sw { display: inline-flex; align-items: center; gap: 8px }
.fm-link { margin-top: 12px }
.fm-tabs { margin: 18px 0 10px }
.fm-list { border: 1px solid var(--line); border-radius: 12px; overflow: hidden }
.fm-list .list-row { width: 100%; padding-left: 14px; padding-right: 14px }
.fm-flag { display: flex; align-items: center; gap: 5px; color: var(--red-ink); font-weight: 600 }
.fm-sec h3 { margin: 0 0 6px; font-size: 14px; color: var(--accent-ink) }
.fm-sec dl { margin: 0; display: grid; gap: 2px }
.fm-sec dt { font-size: 12.5px; color: var(--muted); margin-top: 6px }
.fm-sec dd { margin: 0; font-weight: 600; overflow-wrap: anywhere }
.fm-sum { display: grid; gap: 14px }
.fm-sq { display: grid; gap: 6px }
.fm-st { width: 100%; font-size: 13.5px }
</style>
