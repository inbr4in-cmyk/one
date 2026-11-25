<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { UiButton, UiCard, UiChip, UiEmptyState, UiField, UiIcon, UiModal, UiSelect, UiSkeleton } from '@/components/ui'
import { sessionsApi, trialApi, type Test, type TestKind, type TestSession } from '@/api/assessment'
import { academicsApi, type Group, type Lesson } from '@/api/academics'
import { useAuthStore } from '@/stores/auth'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import { apiErr } from '@/utils/err'
import { addDays, dayLabel, hm, isoDate, schoolNow } from '@/utils/dates'
import { keptRef } from '@/utils/kept'
import type { Locale } from '@/i18n'

/** The bank of tests by level (Progress Test 1, 2, Final) and the tests planned for groups' lessons. */
const props = defineProps<{ tests: Test[] | null; canEdit: boolean }>()
const emit = defineEmits<{ open: [Test]; create: [{ kind: TestKind; title: string; level_id: number }] }>()
const { t, locale } = useI18n()
const loc = computed(() => locale.value as Locale)
const router = useRouter()
const auth = useAuthStore()
const refs = useRefsStore()
const toast = useToastStore()

const levelId = keptRef('tests.level', () => 0)
const levelOpts = computed(() => refs.levels.map((l) => ({ value: l.id, label: l.name })))
watch(() => refs.levels, (ls) => { if (!ls.some((l) => l.id === levelId.value)) levelId.value = ls[0]?.id ?? 0 }, { immediate: true })

/** Each level has its own set: any number of Progress Tests and a Final Test, each with its own questions */
const bank = computed(() => {
  const mine = (props.tests ?? []).filter((x) => x.level_id === levelId.value && (x.kind === 'progress' || x.kind === 'final'))
  const sorted = [...mine].sort((x, y) => Number(x.kind === 'final') - Number(y.kind === 'final') || x.title.localeCompare(y.title, undefined, { numeric: true }))
  const out: { kind: TestKind; title: string; test: Test | null }[] = sorted.map((x) => ({ kind: x.kind, title: x.title, test: x }))
  const titles = new Set(mine.map((x) => x.title.trim().toLowerCase()))
  let n = mine.filter((x) => x.kind === 'progress').length + 1
  while (titles.has(`progress test ${n}`)) n++
  out.push({ kind: 'progress', title: `Progress Test ${n}`, test: null })
  if (!mine.some((x) => x.kind === 'final')) out.push({ kind: 'final', title: 'Final Test', test: null })
  return out
})

/* ---------- planned tests ---------- */
const sessions = ref<TestSession[] | null>(null)
const loadSessions = async () => (sessions.value = await sessionsApi.list().catch(() => []))
onMounted(loadSessions)
const tone = (s: TestSession) => (s.status === 'running' ? 'ok' : s.status === 'planned' ? 'info' : undefined)

/* ---------- «Тестовый режим»: who of the staff has tried the test ---------- */
const trialsOpen = ref(false)
const trials = ref<Awaited<ReturnType<typeof trialApi.list>> | null>(null)
async function openTrials(x: Test) {
  trials.value = null
  trialsOpen.value = true
  trials.value = await trialApi.list(x.id).catch(() => [])
}

/* ---------- «Запланировать тест» ---------- */
const canPlan = computed(() => auth.can('tests.review'))
const planOpen = ref(false)
const groups = ref<Group[]>([])
const lessons = ref<Lesson[]>([])
const pf = reactive({ group_id: 0, test_id: 0, lesson_id: 0 })
const busy = ref(false)
const error = ref<string | null>(null)
async function openPlan() {
  Object.assign(pf, { group_id: 0, test_id: 0, lesson_id: 0 })
  error.value = null
  planOpen.value = true
  groups.value = (await academicsApi.groups().catch(() => [])).filter((g) => g.status !== 'finished' && g.level_id)
}
const group = computed(() => groups.value.find((g) => g.id === pf.group_id) ?? null)
const groupOpts = computed(() => [{ value: 0, label: t('nv.gt.pickGroup') }, ...groups.value.map((g) => ({ value: g.id, label: `${g.name} · ${refs.level(g.level_id)?.name ?? ''}` }))])
const testOpts = computed(() => [{ value: 0, label: t('nv.gt.pickTest') }, ...(props.tests ?? [])
  .filter((x) => group.value && x.level_id === group.value.level_id && (x.kind === 'progress' || x.kind === 'final') && x.questions > 0)
  .map((x) => ({ value: x.id, label: x.title }))])
const lessonOpts = computed(() => [{ value: 0, label: t('nv.gt.pickLesson') }, ...lessons.value.map((l) => ({ value: l.id, label: `${dayLabel(l.starts_at, loc.value, { weekday: 'short', day: 'numeric', month: 'long' })}, ${hm(l.starts_at, loc.value)}${l.plan_title ? ' · ' + l.plan_title : ''}` }))])
watch(() => pf.group_id, async (gid) => {
  pf.test_id = pf.lesson_id = 0
  lessons.value = []
  if (!gid) return
  const from = schoolNow()
  const all = await academicsApi.lessons({ from: isoDate(from), to: isoDate(addDays(from, 45)), group_id: gid }).catch(() => [])
  lessons.value = all.filter((l) => l.status !== 'cancelled' && !l.attendance_marked_at && !l.test_session_id)
  /* the lesson the plan calls a test is offered first */
  const byPlan = lessons.value.find((l) => l.plan_kind && l.plan_kind !== 'lesson')
  if (byPlan) pf.lesson_id = byPlan.id
})
async function plan() {
  if (!pf.group_id || !pf.test_id || !pf.lesson_id) return (error.value = t('nv.gt.fillAll'))
  busy.value = true
  error.value = null
  try {
    await sessionsApi.plan({ ...pf })
    toast.ok(t('nv.gt.planned'))
    planOpen.value = false
    await loadSessions()
  } catch (e) {
    error.value = apiErr(e) ?? t('errors.generic')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiCard :title="t('nv.gt.bank')" icon="tests">
    <template #actions>
      <UiButton v-if="canPlan" variant="primary" icon="calendar-add" @click="openPlan">{{ t('nv.gt.plan') }}</UiButton>
    </template>
    <UiField :label="t('tests.level')" style="max-width: 320px"><UiSelect v-model="levelId" :options="levelOpts" :label="t('tests.level')" block /></UiField>
    <UiSkeleton v-if="!tests" :lines="3" />
    <div v-else class="gt-bank">
      <div v-for="(s, i) in bank" :key="s.test?.id ?? `n${i}`" class="gt-slot" :class="{ empty: !s.test, fin: s.kind === 'final' }" :hidden="!s.test && !canEdit">
        <button type="button" class="gt-main" @click="s.test ? emit('open', s.test) : emit('create', { kind: s.kind, title: s.title, level_id: levelId })">
          <span class="ic"><UiIcon :name="s.kind === 'final' ? 'trophy' : 'tests'" :size="24" /></span>
          <b>{{ s.title }}</b>
          <small v-if="s.test">{{ t('tests.questionsN', { n: s.test.questions }) }}</small>
          <small v-else>{{ t('nv.gt.create') }}</small>
        </button>
        <div v-if="s.test?.staged && canPlan" class="gt-acts">
          <UiButton size="sm" variant="primary" icon="play" :to="`/tests/trial/${s.test.id}`">{{ t('nv.gt.tryIt') }}</UiButton>
          <UiButton size="sm" variant="ghost" @click="openTrials(s.test)">{{ t('nv.gt.results') }}</UiButton>
        </div>
      </div>
    </div>

    <h3 class="gt-h">{{ t('nv.gt.sessions') }}</h3>
    <UiSkeleton v-if="!sessions" :lines="2" />
    <UiEmptyState v-else-if="!sessions.length" icon="calendar-add" :title="t('nv.gt.noSessions')" />
    <div v-else class="gt-list">
      <button v-for="s in sessions" :key="s.id" type="button" class="list-row pick" @click="router.push(`/tests/sessions/${s.id}`)">
        <div class="grow">
          <b>{{ s.group_name }} · {{ s.title }}</b>
          <span v-if="s.lesson_at">{{ dayLabel(s.lesson_at, loc, { weekday: 'short', day: 'numeric', month: 'long' }) }}, {{ hm(s.lesson_at, loc) }}</span>
        </div>
        <UiChip small :tone="tone(s)">{{ t(`nv.gt.st.${s.status}`) }}</UiChip>
        <UiIcon name="arrow" :size="16" class="muted" />
      </button>
    </div>
  </UiCard>

  <UiModal v-model:open="trialsOpen" :title="t('nv.gt.trialMode')">
    <UiSkeleton v-if="!trials" :lines="3" />
    <p v-else-if="!trials.length" class="muted m0">{{ t('nv.gt.noResults') }}</p>
    <RouterLink v-for="x in trials ?? []" :key="x.id" :to="`/tests/attempts/${x.id}`" class="list-row">
      <div class="grow"><b>{{ x.taker }}</b><span v-if="x.finished_at">{{ dayLabel(x.finished_at, loc, { day: 'numeric', month: 'long' }) }}, {{ hm(x.finished_at, loc) }}</span></div>
      <UiChip small :tone="x.status === 'done' ? 'ok' : 'warn'">{{ t(`nv.gt.rs.${x.status}`, x.status) }}</UiChip>
      <b class="num">{{ x.score }}</b>
    </RouterLink>
  </UiModal>

  <UiModal v-model:open="planOpen" :title="t('nv.gt.plan')">
    <div class="stack">
      <UiField :label="t('nv.gt.group')"><UiSelect v-model="pf.group_id" :options="groupOpts" :label="t('nv.gt.group')" block /></UiField>
      <UiField :label="t('nv.gt.test')"><UiSelect v-model="pf.test_id" :options="testOpts" :label="t('nv.gt.test')" block :disabled="!pf.group_id" /></UiField>
      <p v-if="pf.group_id && testOpts.length < 2" class="m0 redc">{{ t('nv.gt.noTests') }}</p>
      <UiField :label="t('nv.gt.lesson')"><UiSelect v-model="pf.lesson_id" :options="lessonOpts" :label="t('nv.gt.lesson')" block :disabled="!pf.group_id" /></UiField>
      <p v-if="error" class="form-err m0" role="alert">{{ error }}</p>
    </div>
    <template #footer="{ close }">
      <UiButton variant="ghost" @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="primary" :loading="busy" @click="plan">{{ t('nv.gt.plan') }}</UiButton>
    </template>
  </UiModal>
</template>

<style scoped>
.gt-bank { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 10px; margin-top: 12px }
.gt-slot { display: flex; flex-direction: column; gap: 10px; padding: 14px; border-radius: 14px; border: 1px solid var(--line); background: var(--surface) }
.gt-slot:hover { border-color: var(--navy-600) }
.gt-main { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; padding: 0; border: 0; background: none; text-align: left; font: inherit; color: var(--ink); cursor: pointer }
.gt-acts { display: flex; gap: 6px; flex-wrap: wrap }
.gt-slot[hidden] { display: none }
.gt-slot[hidden] { display: none }
.gt-slot.empty { border-style: dashed; background: transparent }
.gt-slot .ic { width: 40px; height: 40px; border-radius: 12px; display: grid; place-items: center; background: var(--navy-50); color: var(--accent-ink) }
.gt-slot.fin .ic { background: var(--red-100); color: var(--red-ink) }
.gt-slot small { color: var(--muted); font-size: 12.5px }
.gt-h { margin: 20px 0 8px; font-size: 15px }
.gt-list { border: 1px solid var(--line); border-radius: 12px; overflow: hidden }
.gt-list .list-row { width: 100%; padding-left: 14px; padding-right: 14px }
</style>
