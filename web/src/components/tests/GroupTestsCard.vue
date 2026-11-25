<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { UiButton, UiCard, UiChip, UiEmptyState, UiField, UiIcon, UiModal, UiSelect, UiSkeleton } from '@/components/ui'
import { sessionsApi, type Test, type TestKind, type TestSession } from '@/api/assessment'
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

const SLOTS: { kind: TestKind; title: string }[] = [
  { kind: 'progress', title: 'Progress Test 1' },
  { kind: 'progress', title: 'Progress Test 2' },
  { kind: 'final', title: 'Final Test' },
]
const bank = computed(() => {
  const mine = (props.tests ?? []).filter((x) => x.level_id === levelId.value && (x.kind === 'progress' || x.kind === 'final'))
  const used = new Set<number>()
  const slots = SLOTS.map((s) => {
    const found = mine.find((x) => !used.has(x.id) && x.kind === s.kind && x.title.trim().toLowerCase() === s.title.toLowerCase())
    if (found) used.add(found.id)
    return { ...s, test: found ?? null }
  })
  return [...slots, ...mine.filter((x) => !used.has(x.id)).map((x) => ({ kind: x.kind, title: x.title, test: x as Test | null }))]
})

/* ---------- planned tests ---------- */
const sessions = ref<TestSession[] | null>(null)
const loadSessions = async () => (sessions.value = await sessionsApi.list().catch(() => []))
onMounted(loadSessions)
const tone = (s: TestSession) => (s.status === 'running' ? 'ok' : s.status === 'planned' ? 'info' : undefined)

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
      <button v-for="(s, i) in bank" :key="s.test?.id ?? `n${i}`" type="button" class="gt-slot" :class="{ empty: !s.test, fin: s.kind === 'final' }"
        :disabled="!s.test && !canEdit" @click="s.test ? emit('open', s.test) : emit('create', { kind: s.kind, title: s.title, level_id: levelId })">
        <span class="ic"><UiIcon :name="s.kind === 'final' ? 'trophy' : 'tests'" :size="24" /></span>
        <b>{{ s.title }}</b>
        <small v-if="s.test">{{ t('tests.questionsN', { n: s.test.questions }) }}</small>
        <small v-else>{{ canEdit ? t('nv.gt.create') : t('nv.gt.notMade') }}</small>
      </button>
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
.gt-slot { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; padding: 14px; border-radius: 14px; border: 1px solid var(--line); background: var(--surface); text-align: left; font: inherit; color: var(--ink); cursor: pointer }
.gt-slot:hover:not(:disabled) { border-color: var(--navy-600) }
.gt-slot.empty { border-style: dashed; background: transparent }
.gt-slot .ic { width: 40px; height: 40px; border-radius: 12px; display: grid; place-items: center; background: var(--navy-50); color: var(--accent-ink) }
.gt-slot.fin .ic { background: var(--red-100); color: var(--red-ink) }
.gt-slot small { color: var(--muted); font-size: 12.5px }
.gt-h { margin: 20px 0 8px; font-size: 15px }
.gt-list { border: 1px solid var(--line); border-radius: 12px; overflow: hidden }
.gt-list .list-row { width: 100%; padding-left: 14px; padding-right: 14px }
</style>
