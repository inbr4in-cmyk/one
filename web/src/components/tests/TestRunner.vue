<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import BrandLogo from '@/components/layout/BrandLogo.vue'
import { UiButton, UiIcon, UiInput, UiSkeleton, UiTextarea } from '@/components/ui'
import type { MyTestState, StageAnswers, TestOutline } from '@/api/assessment'
import { nowMs } from '@/utils/clock'
import { apiErr } from '@/utils/err'

/**
 * Taking a test online. A plain test goes one question at a time; a staged test goes stage by stage, every stage one
 * page with its own time, the same order for everyone. There is no way back, the clock and the keys live on the
 * server. Leaving the page (another tab, minimised window) annuls the attempt until it is restored. Text cannot be
 * copied. Speaking answers are recorded by the camera and kept on the server.
 */
export interface RunnerApi {
  state: () => Promise<MyTestState | null>
  begin: () => Promise<MyTestState>
  answer?: (questionId: number, answer: number[] | string) => Promise<MyTestState>
  save: (partId: string, answers: StageAnswers, final: boolean) => Promise<MyTestState>
  video: (questionId: number, file: Blob) => Promise<MyTestState>
  leave: () => Promise<MyTestState>
  /** Only in the staff's trial run: with students the teacher restores */
  restore?: () => Promise<MyTestState>
}
const props = defineProps<{ api: RunnerApi; title?: string; outline?: TestOutline | null; exitTo: string; resultTo?: (attemptId: number) => string }>()
const { t } = useI18n()

const st = ref<MyTestState | null>(null)
const missing = ref(false)
const busy = ref(false)
const error = ref<string | null>(null)
const tick = ref(nowMs())
let clock: ReturnType<typeof setInterval> | null = null
let poll: ReturnType<typeof setInterval> | null = null
let autosave: ReturnType<typeof setInterval> | null = null

const a = computed(() => st.value?.attempt ?? null)
const q = computed(() => st.value?.question ?? null)
const stage = computed(() => st.value?.stage ?? null)
const outline = computed(() => st.value?.outline ?? props.outline ?? null)
const running = computed(() => !st.value || st.value.status === 'running')
const taking = computed(() => !!st.value && st.value.status === 'running' && a.value?.status === 'in_progress' && (!!q.value || !!stage.value))
const view = computed(() => {
  if (missing.value) return 'missing'
  if (!st.value && !props.outline) return 'loading'
  if (a.value?.status === 'void') return 'void'
  if (a.value && (a.value.status === 'done' || a.value.status === 'needs_review')) return 'done'
  if (st.value?.status === 'finished') return 'over'
  if (taking.value) return stage.value ? 'stage' : 'test'
  return 'intro'
})
const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
const until = (iso: string | null | undefined) => (iso ? Math.max(0, Math.ceil((new Date(iso).getTime() - tick.value) / 1000)) : null)
const leftS = computed(() => until(stage.value ? stage.value.ends_at : st.value?.ends_at))
const leftLabel = computed(() => (leftS.value === null ? '' : mmss(leftS.value)))
const pct = computed(() => (a.value?.total ? Math.round((a.value.position / a.value.total) * 100) : 0))
const dur = computed(() => {
  const d = a.value?.duration_sec
  return d == null ? '—' : t('nv.gt.min', { m: Math.floor(d / 60), s: d % 60 })
})

/* ---------- answers ---------- */
const picked = ref<number[]>([])
const text = ref('')
const ans = reactive<Record<string, number[] | string>>({})
let dirty = false
let stageId = ''
function take(s: MyTestState | null) {
  if (!s) return
  if (s.question?.id !== st.value?.question?.id) {
    picked.value = []
    text.value = ''
  }
  const sg = s.stage ?? null
  if (sg && sg.id !== stageId) {
    Object.keys(ans).forEach((k) => delete ans[k])
    for (const [k, v] of Object.entries(sg.draft)) if (typeof v === 'string' || Array.isArray(v)) ans[k] = v
    dirty = false
    window.scrollTo({ top: 0 })
  }
  stageId = sg?.id ?? ''
  st.value = s
}
async function load() {
  try {
    take(await props.api.state())
  } catch {
    if (!st.value && !props.outline) missing.value = true
  }
}
async function run<T>(fn: () => Promise<T>): Promise<T | undefined> {
  busy.value = true
  error.value = null
  try {
    return await fn()
  } catch (e) {
    error.value = apiErr(e) ?? t('errors.generic')
    return undefined
  } finally {
    busy.value = false
  }
}
const begin = () => run(async () => take(await props.api.begin()))
function pick(i: number) {
  if (!q.value) return
  error.value = null
  picked.value = q.value.kind === 'multi' ? (picked.value.includes(i) ? picked.value.filter((x) => x !== i) : [...picked.value, i]) : [i]
}
async function next() {
  if (!q.value || busy.value || !props.api.answer) return
  const answer = q.value.kind === 'text' ? text.value.trim() : picked.value
  if (!answer.length) return (error.value = t('nv.gt.pickAnswer'))
  const id = q.value.id
  if ((await run(async () => take(await props.api.answer!(id, answer)))) === undefined) await load()
  window.scrollTo({ top: 0 })
}

/* ---------- a stage ---------- */
const isPicked = (id: number, i: number) => Array.isArray(ans[id]) && (ans[id] as number[]).includes(i)
function choose(id: number, kind: string, i: number) {
  const cur = Array.isArray(ans[id]) ? (ans[id] as number[]) : []
  ans[id] = kind === 'multi' ? (cur.includes(i) ? cur.filter((x) => x !== i) : [...cur, i]) : [i]
  dirty = true
}
const typed = (id: number) => (typeof ans[id] === 'string' ? (ans[id] as string) : '')
function type(id: number, v: string) {
  ans[id] = v
  dirty = true
}
const payload = (): StageAnswers => Object.fromEntries((stage.value?.questions ?? []).filter((x) => x.kind !== 'video').map((x) => [String(x.id), ans[x.id] ?? null]))
async function saveStage(final: boolean) {
  const sg = stage.value
  if (!sg || (busy.value && !final)) return
  if (!final) {
    if (!dirty) return
    dirty = false
    props.api.save(sg.id, payload(), false).catch(() => (dirty = true))
    return
  }
  await run(async () => take(await props.api.save(sg.id, payload(), true)))
}
const videoQs = computed(() => (stage.value?.questions ?? []).filter((x) => x.kind === 'video'))
const isSpeaking = computed(() => videoQs.value.length > 0)
const vq = computed(() => videoQs.value.find((x) => !stage.value?.draft[String(x.id)]) ?? null)
const vNo = computed(() => (vq.value ? videoQs.value.indexOf(vq.value) + 1 : videoQs.value.length))

/* ---------- camera ---------- */
const stream = ref<MediaStream | null>(null)
const camError = ref<string | null>(null)
const preview = ref<HTMLVideoElement | null>(null)
let asking = false
async function openCamera() {
  camError.value = null
  asking = true
  try {
    stream.value = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' }, audio: true })
  } catch {
    camError.value = t('nv.gt.camDenied')
  } finally {
    // the browser's permission prompt takes the focus away: that is not leaving the test
    setTimeout(() => (asking = false), 600)
  }
}
watch([stream, preview], ([s, el]) => {
  if (el && s && el.srcObject !== s) el.srcObject = s
})
const recording = ref(false)
const uploading = ref(false)
const recLeft = ref(0)
let rec: MediaRecorder | null = null
let chunks: Blob[] = []
let finishAfter = false
function startRec() {
  if (!stream.value || !vq.value || recording.value) return
  const qid = vq.value.id
  const mime = ['video/webm;codecs=vp8,opus', 'video/webm', 'video/mp4'].find((m) => window.MediaRecorder?.isTypeSupported(m))
  if (!mime) return (camError.value = t('nv.gt.camUnsupported'))
  chunks = []
  rec = new MediaRecorder(stream.value, { mimeType: mime, videoBitsPerSecond: 450_000, audioBitsPerSecond: 48_000 })
  rec.ondataavailable = (e) => e.data.size && chunks.push(e.data)
  rec.onstop = async () => {
    recording.value = false
    uploading.value = true
    const file = new Blob(chunks, { type: mime.split(';')[0] })
    await run(async () => take(await props.api.video(qid, file)))
    uploading.value = false
    if (finishAfter || (!vq.value && stage.value)) {
      finishAfter = false
      await saveStage(true)
    }
  }
  rec.start(1000)
  recording.value = true
  recLeft.value = stage.value?.seconds ?? 100
}
const stopRec = () => rec && rec.state !== 'inactive' && rec.stop()

/* ---------- time ---------- */
watch(leftS, (v) => {
  if (v !== 0 || !taking.value) return
  if (!stage.value) return void load()
  if (recording.value) {
    finishAfter = true
    stopRec()
  } else if (!uploading.value) saveStage(true)
})

/* ---------- leaving the page annuls the attempt ---------- */
function left() {
  if (!taking.value || asking) return
  if (recording.value) {
    rec!.onstop = null
    stopRec()
    recording.value = false
  }
  const sg = stage.value
  const typed = sg && dirty ? props.api.save(sg.id, payload(), false).catch(() => undefined) : Promise.resolve(undefined)
  if (st.value?.attempt) st.value = { ...st.value, attempt: { ...st.value.attempt, status: 'void' }, question: null, stage: null }
  stageId = ''
  typed.then(() => props.api.leave()).then(take).catch(() => undefined)
}
const onHide = () => document.visibilityState === 'hidden' && left()
const restore = () => run(async () => take(await props.api.restore!()))
const block = (e: Event) => e.preventDefault()

onMounted(async () => {
  await load()
  document.addEventListener('visibilitychange', onHide)
  window.addEventListener('blur', left)
  window.addEventListener('pagehide', left)
  clock = setInterval(() => {
    tick.value = nowMs()
    if (recording.value && --recLeft.value <= 0) stopRec()
  }, 1000)
  /* waits for the teacher: the start, a restore after annulment, the end */
  poll = setInterval(() => st.value && !taking.value && st.value.status !== 'finished' && view.value !== 'done' && view.value !== 'missing' && load(), 4000)
  autosave = setInterval(() => saveStage(false), 12000)
})
onBeforeUnmount(() => {
  left()
  document.removeEventListener('visibilitychange', onHide)
  window.removeEventListener('blur', left)
  window.removeEventListener('pagehide', left)
  for (const x of [clock, poll, autosave]) if (x) clearInterval(x)
  stream.value?.getTracks().forEach((x) => x.stop())
})
</script>

<template>
  <div class="pt tr-nocopy" @copy="block" @cut="block" @paste="block" @contextmenu="block" @dragstart="block">
    <header class="pt-top">
      <BrandLogo :size="34" :tagline="false" /><span class="sp" />
      <span v-if="view === 'stage' && leftLabel" class="tr-clock num" :class="{ low: (leftS ?? 0) < 60 }" role="timer"><UiIcon name="clock" :size="18" />{{ leftLabel }}</span>
    </header>
    <main class="pt-main" :class="{ wide: view === 'stage' }">
      <section v-if="view === 'loading'" class="card pt-card"><UiSkeleton :lines="6" /></section>

      <section v-else-if="view === 'missing'" class="card pt-card pt-center">
        <UiIcon name="tests" :size="40" class="pt-big-ico" />
        <h1>{{ t('nv.gt.notYours') }}</h1>
        <UiButton :to="exitTo">{{ t('nv.gt.toCabinet') }}</UiButton>
      </section>

      <section v-else-if="view === 'intro'" class="card pt-card">
        <h1>{{ st?.title ?? title }}</h1>
        <p class="pt-meta">
          <span><UiIcon name="clock" :size="16" />{{ t('nv.gt.introT', { n: outline?.minutes ?? st?.time_limit_min ?? 60 }) }}</span>
          <span v-if="st?.status === 'running' && !outline && leftLabel"><UiIcon name="clock" :size="16" />{{ t('nv.gt.left', { t: leftLabel }) }}</span>
        </p>
        <ol v-if="outline" class="tr-outline">
          <li v-for="(s, i) in outline.stages" :key="i"><span>{{ s.section }}<template v-if="s.title && s.title !== s.section"> · {{ s.title }}</template></span><b class="num">{{ t('nv.gt.minN', { n: s.minutes }) }}</b></li>
        </ol>
        <ul class="tr-rules"><li>{{ t('nv.gt.rule1') }}</li><li>{{ t('nv.gt.rule2') }}</li><li v-if="outline">{{ t('nv.gt.rule3') }}</li></ul>
        <div v-if="outline?.camera" class="tr-cam-ask">
          <video v-if="stream" ref="preview" autoplay muted playsinline class="tr-video small" />
          <div class="grow"><b>{{ t('nv.gt.camTitle') }}</b>
            <span v-if="stream" class="tr-ok"><UiIcon name="ok" :size="16" />{{ t('nv.gt.camOk') }}</span>
            <UiButton v-else size="sm" icon="play" @click="openCamera">{{ t('nv.gt.camAllow') }}</UiButton>
          </div>
        </div>
        <p v-if="camError" class="form-err" role="alert">{{ camError }}</p>
        <p v-if="error" class="form-err" role="alert">{{ error }}</p>
        <UiButton v-if="running" variant="primary" size="lg" block icon-end="arrow" :loading="busy" :disabled="!!outline?.camera && !stream" @click="begin">{{ t('nv.gt.begin') }}</UiButton>
        <p v-else class="tr-wait" role="status"><UiIcon name="clock" :size="18" />{{ t('nv.gt.waitStart') }}</p>
      </section>

      <!-- a plain test: one question at a time -->
      <section v-else-if="view === 'test' && q && a" class="card pt-card" :aria-busy="busy">
        <div class="pt-prog">
          <span>{{ t('nv.gt.qOf', { n: a.position + 1, total: a.total }) }}</span>
          <span class="sp" />
          <span v-if="leftLabel" class="chip" :class="{ red: (leftS ?? 0) < 60 }" role="timer"><UiIcon name="clock" :size="16" />{{ t('nv.gt.left', { t: leftLabel }) }}</span>
        </div>
        <div class="bar-track" role="progressbar" :aria-valuenow="pct" aria-valuemin="0" aria-valuemax="100"><i :style="{ width: `${pct}%` }" /></div>
        <fieldset :key="q.id" class="pt-q">
          <legend>{{ q.text }}</legend>
          <UiTextarea v-if="q.kind === 'text'" v-model="text" :placeholder="t('placement.answerPh')" :aria-label="q.text" :rows="4" :maxlength="2000" />
          <div v-else class="pt-opts">
            <label v-for="(o, i) in q.options" :key="i" class="pt-opt" :class="{ on: picked.includes(i) }">
              <input :type="q.kind === 'multi' ? 'checkbox' : 'radio'" :name="`q${q.id}`" :checked="picked.includes(i)" @change="pick(i)" />
              <span class="pt-mark" :class="q.kind" aria-hidden="true" />
              <span class="pt-otext">{{ o }}</span>
            </label>
          </div>
        </fieldset>
        <p v-if="error" class="form-err" role="alert">{{ error }}</p>
        <div class="pt-nav"><span class="sp" /><UiButton variant="primary" size="lg" icon-end="arrow" :loading="busy" @click="next">{{ t('nv.gt.next') }}</UiButton></div>
      </section>

      <!-- a staged test: one stage on a page -->
      <section v-else-if="view === 'stage' && stage" :key="stage.id" class="card pt-card" :aria-busy="busy">
        <div class="pt-prog"><span>{{ t('nv.gt.stageOf', { n: stage.index + 1, total: stage.total }) }}</span><span class="sp" /><span class="chip">{{ stage.section }}</span></div>
        <div class="bar-track" role="progressbar" :aria-valuenow="pct" aria-valuemin="0" aria-valuemax="100"><i :style="{ width: `${pct}%` }" /></div>
        <h1>{{ stage.title }}</h1>
        <p v-if="stage.hint" class="muted pt-intro">{{ stage.hint }}</p>
        <div v-if="stage.words" class="tr-words"><span v-for="w in stage.words" :key="w">{{ w }}</span></div>
        <article v-if="stage.text" class="tr-text"><h2 v-if="stage.text_title">{{ stage.text_title }}</h2><p>{{ stage.text }}</p></article>
        <audio v-if="stage.audio" :src="stage.audio" controls controlsList="nodownload noplaybackrate" preload="auto" class="tr-audio" />

        <template v-if="isSpeaking">
          <div v-if="vq" class="tr-speak">
            <p class="tr-vno">{{ t('nv.gt.qOf', { n: vNo, total: videoQs.length }) }}</p>
            <h2 class="tr-vq">{{ vq.text }}</h2>
            <video v-if="stream" ref="preview" autoplay muted playsinline class="tr-video" :class="{ rec: recording }" />
            <p v-if="camError" class="form-err" role="alert">{{ camError }}</p>
            <UiButton v-if="!stream" icon="play" @click="openCamera">{{ t('nv.gt.camAllow') }}</UiButton>
            <UiButton v-else-if="!recording && !uploading" variant="primary" size="lg" icon="play" @click="startRec">{{ t('nv.gt.recStart') }}</UiButton>
            <template v-else-if="recording">
              <p class="tr-rec num" role="timer"><i />{{ t('nv.gt.recLeft', { t: mmss(Math.max(0, recLeft)) }) }}</p>
              <UiButton variant="primary" size="lg" icon-end="arrow" @click="stopRec">{{ t('nv.gt.recStop') }}</UiButton>
            </template>
            <p v-else class="tr-wait" role="status"><UiIcon name="clock" :size="18" />{{ t('nv.gt.recSaving') }}</p>
          </div>
        </template>
        <template v-else>
          <fieldset v-for="(x, n) in stage.questions" :key="x.id" class="pt-q tr-q">
            <legend><span class="tr-n num">{{ n + 1 }}.</span> {{ x.text }}</legend>
            <UiTextarea v-if="x.kind === 'text'" :model-value="typed(x.id)" :aria-label="x.text" :rows="4" :maxlength="2000" autocomplete="off" spellcheck="false" @update:model-value="type(x.id, String($event))" />
            <UiInput v-else-if="x.kind === 'input'" :model-value="typed(x.id)" :aria-label="x.text" :maxlength="200" autocomplete="off" autocapitalize="off" spellcheck="false" @update:model-value="type(x.id, String($event))" />
            <div v-else class="pt-opts" :class="{ row: x.options.length <= 3 && x.options.every((o) => o.length < 22) }">
              <label v-for="(o, i) in x.options" :key="i" class="pt-opt" :class="{ on: isPicked(x.id, i) }">
                <input :type="x.kind === 'multi' ? 'checkbox' : 'radio'" :name="`q${x.id}`" :checked="isPicked(x.id, i)" @change="choose(x.id, x.kind, i)" />
                <span class="pt-mark" :class="x.kind" aria-hidden="true" />
                <span class="pt-otext">{{ o }}</span>
              </label>
            </div>
          </fieldset>
        </template>

        <p v-if="error" class="form-err" role="alert">{{ error }}</p>
        <div v-if="!isSpeaking" class="pt-nav">
          <span class="muted tr-noback">{{ t('nv.gt.noBack') }}</span><span class="sp" />
          <UiButton variant="primary" size="lg" icon-end="arrow" :loading="busy" @click="saveStage(true)">{{ stage.index + 1 < stage.total ? t('nv.gt.nextStage') : t('nv.gt.finishTest') }}</UiButton>
        </div>
      </section>

      <section v-else-if="view === 'void'" class="card pt-card pt-center" role="alert">
        <span class="pt-done-ico tr-red"><UiIcon name="lock" :size="40" /></span>
        <h1>{{ t('nv.gt.voidTitle') }}</h1>
        <p class="muted">{{ api.restore ? t('nv.gt.voidTrial') : t('nv.gt.voidText') }}</p>
        <UiButton v-if="api.restore && st?.status === 'running'" variant="primary" :loading="busy" @click="restore">{{ t('nv.gt.restore') }}</UiButton>
      </section>

      <section v-else class="card pt-card pt-center">
        <span class="pt-done-ico"><UiIcon name="trophy" :size="40" /></span>
        <h1>{{ t('nv.gt.doneTitle') }}</h1>
        <div v-if="a && a.status === 'done'" class="pt-res">
          <div><small>{{ t('nv.gt.yourScore') }}</small><b class="num">{{ a.score }} / {{ a.max_score }}</b></div>
          <div><small>{{ t('nv.gt.yourTime') }}</small><b class="num">{{ dur }}</b></div>
        </div>
        <p v-else-if="a" class="muted">{{ t('nv.gt.reviewText') }}</p>
        <UiButton v-if="a && resultTo" variant="primary" :to="resultTo(a.id)">{{ t('nv.gt.seeAnswers') }}</UiButton>
        <UiButton :to="exitTo">{{ t('nv.gt.toCabinet') }}</UiButton>
      </section>
    </main>
  </div>
</template>

<style scoped>
.tr-nocopy { -webkit-user-select: none; user-select: none; -webkit-touch-callout: none }
.tr-nocopy :is(input, textarea) { -webkit-user-select: text; user-select: text }
.pt-main.wide { max-width: 820px }
.tr-clock { display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 999px; background: color-mix(in srgb, var(--side-ink) 14%, transparent); color: var(--side-ink); font-weight: 700; font-size: 16px }
.tr-clock.low { background: var(--red); color: #fff }
.tr-outline { margin: 0; padding: 0; list-style: none; border: 1px solid var(--line); border-radius: 12px; overflow: hidden }
.tr-outline li { display: flex; justify-content: space-between; gap: 12px; padding: 8px 12px; font-size: 14px }
.tr-outline li + li { border-top: 1px solid var(--line) }
.tr-rules { margin: 0; padding-left: 20px; display: grid; gap: 4px; font-weight: 600 }
.tr-wait { margin: 0; display: flex; align-items: center; gap: 8px; color: var(--muted) }
.tr-red { background: var(--red-100); color: var(--red-ink) }
.tr-cam-ask { display: flex; align-items: center; gap: 12px; padding: 12px; border: 1px solid var(--line); border-radius: 12px }
.tr-cam-ask .grow { display: grid; gap: 6px; justify-items: start }
.tr-ok { display: inline-flex; align-items: center; gap: 6px; color: var(--ok); font-weight: 600 }
.tr-video { width: 100%; max-width: 420px; aspect-ratio: 4 / 3; border-radius: 14px; background: #000; object-fit: cover; transform: scaleX(-1) }
.tr-video.small { width: 96px; border-radius: 10px }
.tr-video.rec { outline: 3px solid var(--red) }
.tr-words { display: flex; flex-wrap: wrap; gap: 6px; padding: 12px; border-radius: 12px; background: var(--navy-50); border: 1px solid var(--line) }
.tr-words span { padding: 4px 10px; border-radius: 999px; background: var(--surface); border: 1px solid var(--line); font-weight: 600; font-size: 14px }
.tr-text { padding: 14px 16px; border-radius: 12px; background: var(--navy-50); border: 1px solid var(--line) }
.tr-text h2 { margin: 0 0 8px; font-size: 16px }
.tr-text p { margin: 0; white-space: pre-wrap; line-height: 1.55 }
.tr-audio { width: 100% }
.tr-q { padding-top: 4px }
.tr-q :deep(legend), .tr-q legend { font-size: 15.5px; margin-bottom: 8px }
.tr-n { color: var(--muted) }
.pt-opts.row { display: flex; flex-wrap: wrap }
.pt-opts.row .pt-opt { flex: 1 1 140px }
.tr-noback { font-size: 12.5px }
.tr-speak { display: grid; gap: 12px; justify-items: center; text-align: center }
.tr-vno { margin: 0; color: var(--muted); font-size: 13px }
.tr-vq { margin: 0; font-size: 20px; line-height: 1.35 }
.tr-rec { margin: 0; display: inline-flex; align-items: center; gap: 8px; font-weight: 700; color: var(--red-ink) }
.tr-rec i { width: 10px; height: 10px; border-radius: 50%; background: var(--red); animation: tr-blink 1s infinite }
@keyframes tr-blink { 50% { opacity: .2 } }
</style>
