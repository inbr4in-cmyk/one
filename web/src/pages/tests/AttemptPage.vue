<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { UiButton, UiCard, UiChip, UiEmptyState, UiIcon, UiSkeleton } from '@/components/ui'
import { attemptsApi, type AttemptDetail, type AttemptItem } from '@/api/assessment'
import { useToastStore } from '@/stores/toast'

/** One attempt for who checks it: every answer against the key; writing and speaking get their points by hand. */
const { t } = useI18n()
const route = useRoute()
const toast = useToastStore()
const d = ref<AttemptDetail | null>(null)
const missing = ref(false)
const marks = reactive<Record<string, number>>({})
const videos = reactive<Record<number, string>>({})
const loadingVideo = ref<number | null>(null)
const busy = ref(false)

function take(x: AttemptDetail) {
  d.value = x
  for (const p of x.parts) for (const it of p.items) if (it.right === null && it.mark !== null) marks[it.id] = it.mark
}
onMounted(async () => {
  try {
    take(await attemptsApi.detail(Number(route.params.id)))
  } catch {
    missing.value = true
  }
})
onBeforeUnmount(() => Object.values(videos).forEach((u) => URL.revokeObjectURL(u)))

const answered = (it: AttemptItem) => !!it.answer || it.video
const manual = computed(() => (d.value?.parts ?? []).flatMap((p) => p.items).filter((it) => it.right === null && answered(it)))
const dur = computed(() => (d.value?.duration_sec == null ? '—' : t('nv.gt.min', { m: Math.floor(d.value.duration_sec / 60), s: d.value.duration_sec % 60 })))
async function play(it: AttemptItem) {
  if (!d.value || videos[it.id]) return
  loadingVideo.value = it.id
  try {
    videos[it.id] = URL.createObjectURL(await attemptsApi.video(d.value.id, it.id))
  } catch {
    toast.error(t('errors.generic'))
  } finally {
    loadingVideo.value = null
  }
}
async function save() {
  if (!d.value) return
  busy.value = true
  try {
    take(await attemptsApi.marks(d.value.id, Object.fromEntries(manual.value.filter((it) => marks[it.id] !== undefined).map((it) => [String(it.id), marks[it.id] as number]))))
    toast.ok(t('common.saved'))
  } catch {
    /* toast shown by the client */
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiEmptyState v-if="missing" large icon="tests" :title="t('nv.gt.notYours')" />
  <div v-else-if="!d" class="card card-pad"><UiSkeleton :lines="8" /></div>
  <div v-else class="grid">
    <UiCard>
      <div class="at-head">
        <div class="grow">
          <h2 class="h-display at-title">{{ d.title }}</h2>
          <p class="m0 muted">{{ d.taker }}<template v-if="d.trial"> · {{ t('nv.gt.trialMode') }}</template> · {{ dur }}</p>
        </div>
        <UiChip :tone="d.status === 'done' ? 'ok' : d.status === 'void' ? 'red' : 'warn'">{{ t(`nv.gt.rs.${d.status}`, d.status) }}</UiChip>
        <b class="at-score num">{{ d.score }} <small>/ {{ d.max_score }}</small></b>
      </div>
      <div class="at-parts">
        <span v-for="p in d.parts" :key="p.id ?? 'x'" class="chip">{{ p.section }}<template v-if="p.title && p.title !== p.section"> · {{ p.title }}</template>: <b class="num">{{ p.score }} / {{ p.max }}</b></span>
      </div>
    </UiCard>

    <UiCard v-for="p in d.parts" :key="p.id ?? 'x'" :title="[p.section, p.title !== p.section ? p.title : null].filter(Boolean).join(' · ')">
      <template #actions><b class="num">{{ p.score }} / {{ p.max }}</b></template>
      <ol class="at-list">
        <li v-for="it in p.items" :key="it.id" :class="{ ok: it.right === true, bad: it.right === false }">
          <p class="at-q">{{ it.text }}</p>
          <template v-if="it.right !== null">
            <p class="at-a"><UiIcon :name="it.right ? 'ok' : 'x'" :size="16" /><b>{{ it.answer ?? t('nv.gt.noAnswer') }}</b><span v-if="!it.right" class="muted"> · {{ t('nv.gt.key') }}: {{ it.key }}</span></p>
          </template>
          <template v-else>
            <p v-if="it.answer" class="at-text">{{ it.answer }}</p>
            <template v-else-if="it.video">
              <video v-if="videos[it.id]" :src="videos[it.id]" controls playsinline class="at-video" />
              <UiButton v-else size="sm" icon="play" :loading="loadingVideo === it.id" @click="play(it)">{{ t('nv.gt.watch') }}</UiButton>
            </template>
            <p v-else class="muted m0">{{ t('nv.gt.noAnswer') }}</p>
            <div v-if="answered(it)" class="at-marks" role="group" :aria-label="t('nv.gt.score')">
              <span class="muted">{{ t('nv.gt.score') }}:</span>
              <button v-for="n in it.points + 1" :key="n" type="button" :class="{ on: marks[it.id] === n - 1 }" :aria-pressed="marks[it.id] === n - 1" @click="marks[it.id] = n - 1">{{ n - 1 }}</button>
            </div>
          </template>
        </li>
      </ol>
    </UiCard>

    <div v-if="manual.length" class="at-save"><UiButton variant="primary" size="lg" icon="ok" :loading="busy" @click="save">{{ t('nv.gt.saveMarks') }}</UiButton></div>
  </div>
</template>

<style scoped>
.at-head { display: flex; align-items: center; gap: 14px; flex-wrap: wrap }
.at-title { font-size: 20px; margin: 0 }
.at-score { font-family: var(--font-display); font-size: 28px }
.at-score small { font-size: 15px; color: var(--muted) }
.at-parts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px }
.at-list { margin: 0; padding-left: 22px; display: grid; gap: 12px }
.at-q { margin: 0; white-space: pre-wrap }
.at-a { margin: 4px 0 0; display: flex; align-items: center; gap: 6px; flex-wrap: wrap }
li.ok .at-a { color: var(--ok) }
li.bad .at-a b { color: var(--red-ink) }
.at-text { margin: 6px 0 0; padding: 10px 12px; border-radius: 10px; background: var(--navy-50); border: 1px solid var(--line); white-space: pre-wrap }
.at-video { display: block; margin-top: 6px; width: 100%; max-width: 420px; border-radius: 12px; background: #000 }
.at-marks { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-top: 8px }
.at-marks button { min-width: 36px; min-height: 36px; border-radius: 9px; border: 1px solid var(--line); background: var(--surface); font: inherit; font-weight: 600; color: var(--ink); cursor: pointer }
.at-marks button.on { background: var(--btn-navy); border-color: var(--btn-navy); color: var(--on-accent) }
.at-save { display: flex; justify-content: flex-end }
</style>
