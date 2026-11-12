<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiCard, UiChip, UiEmptyState, UiIcon, UiSegmented, UiSelect } from '@/components/ui'
import { oldCrmApi, type ImportFileResult, type ImportResult, type ImportRow, type ImportStatus, type ImportTotals } from '@/api/oldCrm'
import OldCrmAnnulCard from '@/components/settings/OldCrmAnnulCard.vue'
import { useRefsStore } from '@/stores/refs'
import { money } from '@/utils/dates'
import { apiErr } from '@/utils/err'
import type { Locale } from '@/i18n'

/**
 * Import from the old CRM: drop several exports, see the detected kind of each (override if needed), check (dry run:
 * every row with new / update / skip / error and the reason), then «Загрузить» and see what was written.
 */
const { t, te, locale } = useI18n()
const refs = useRefsStore()
refs.load()
const loc = computed(() => locale.value as Locale)

const KINDS = ['teachers', 'groups', 'students', 'individual', 'schedule', 'attendance', 'payments', 'library', 'communications',
  'test_results', 'homework_plans'] as const
const MAX_MB = 10
const PAGE = 50
const STATUSES: ImportStatus[] = ['new', 'update', 'skip', 'error']
const TONE: Record<ImportStatus, 'ok' | 'info' | undefined | 'red'> = { new: 'ok', update: 'info', skip: undefined, error: 'red' }

interface Picked { file: File; kind: string }
const picked = ref<Picked[]>([])
const branchId = ref<number>(0)
const preview = ref<ImportResult | null>(null)
const result = ref<ImportResult | null>(null)
const busy = ref<'check' | 'commit' | null>(null)
const error = ref<string | null>(null)
const dragging = ref(false)
const input = ref<HTMLInputElement | null>(null)
/** What the shown preview was made for: any change to files, kinds or branch makes it stale. */
const previewKey = ref('')
const key = computed(() => JSON.stringify([picked.value.map((p) => [p.file.name, p.file.size, p.file.lastModified, p.kind]), branchId.value]))
const stale = computed(() => !!preview.value && previewKey.value !== key.value)
const filter = reactive<Record<string, ImportStatus | 'all'>>({})
const shown = reactive<Record<string, number>>({})

const kindLabel = (k: string | null | undefined) => (k && te(`oldCrm.kind.${k}`) ? t(`oldCrm.kind.${k}`) : k ?? '—')
const kindOptions = computed(() => [{ value: '', label: t('oldCrm.kindAuto') }, ...KINDS.map((k) => ({ value: k, label: kindLabel(k) }))])
const branchOptions = computed(() => [{ value: 0, label: t('oldCrm.noBranch') }, ...refs.branches.map((b) => ({ value: b.id, label: b.name }))])
const statLabel = (k: string) => (te(`oldCrm.stat.${k}`) ? t(`oldCrm.stat.${k}`) : k)
const statValue = (k: string, v: number) => (k === 'payments_sum' ? money(v, loc.value) : v.toLocaleString(loc.value === 'kk' ? 'kk-KZ' : 'ru-RU'))
const size = (b: number) => (b > 1024 * 1024 ? `${(b / 1024 / 1024).toFixed(1)} МБ` : `${Math.max(1, Math.round(b / 1024))} КБ`)

function add(list: FileList | File[] | null | undefined) {
  if (!list) return
  const bad: string[] = []
  for (const f of Array.from(list)) {
    if (!/\.(xlsx|csv)$/i.test(f.name)) {
      bad.push(f.name)
      continue
    }
    const i = picked.value.findIndex((p) => p.file.name === f.name)
    if (i >= 0) picked.value.splice(i, 1, { file: f, kind: picked.value[i]?.kind ?? '' })
    else picked.value.push({ file: f, kind: '' })
  }
  error.value = bad.length ? `${t('oldCrm.onlyTypes')}: ${bad.join(', ')}` : null
  result.value = null
  if (input.value) input.value.value = ''
}
function onDrop(e: DragEvent) {
  dragging.value = false
  add(e.dataTransfer?.files)
}
function removeAt(i: number) {
  picked.value.splice(i, 1)
  if (!picked.value.length) preview.value = null
}
function fileResult(i: number): ImportFileResult | undefined {
  return (result.value ?? preview.value)?.files.find((f) => f.index === i)
}

async function run(commit: boolean) {
  if (!picked.value.length) return
  busy.value = commit ? 'commit' : 'check'
  error.value = null
  const k = key.value
  try {
    const r = await oldCrmApi.run(picked.value.map((p) => p.file), picked.value.map((p) => p.kind), branchId.value || null, commit)
    if (commit) {
      result.value = r
      preview.value = null
    } else {
      preview.value = r
      previewKey.value = k
    }
    for (const s of Object.keys(filter)) delete filter[s]
    for (const s of Object.keys(shown)) delete shown[s]
  } catch (e) {
    error.value = apiErr(e) ?? t('errors.generic')
  } finally {
    busy.value = null
  }
}
function reset() {
  picked.value = []
  preview.value = null
  result.value = null
  error.value = null
}

const view = computed(() => result.value ?? preview.value)
/** Sections in the order the server ran them: reference data first, then the files. */
const sections = computed(() => {
  const v = view.value
  if (!v) return []
  const out: { id: string; title: string; sub: string | null; totals: ImportTotals; rows: ImportRow[]; error: string | null; stats: Record<string, number>; ms: number }[] = []
  if (v.refs.rows.length) out.push({ id: 'refs', title: t('oldCrm.refs'), sub: null, totals: v.refs.totals, rows: v.refs.rows, error: null, stats: {}, ms: 0 })
  const ordered = [...v.order.map((i) => v.files.find((f) => f.index === i)!), ...v.files.filter((f) => !v.order.includes(f.index))]
  for (const f of ordered) {
    const sub = [f.filename, f.header_row ? t('oldCrm.header', { n: f.header_row }) : null, f.info.period ?? null].filter(Boolean).join(' · ')
    out.push({ id: `f${f.index}`, title: f.kind ? kindLabel(f.kind) : t('oldCrm.fileError'), sub, totals: f.totals, rows: f.rows,
      error: f.error, stats: f.stats, ms: f.ms })
  }
  return out
})
function rowsOf(id: string, rows: ImportRow[]) {
  const st = filter[id] ?? 'all'
  return st === 'all' ? rows : rows.filter((r) => r.status === st)
}
const filterOptions = (totals: ImportTotals, all: number) => [
  { value: 'all' as const, label: `${t('oldCrm.status.all')} ${all}` },
  ...STATUSES.filter((s) => totals[s]).map((s) => ({ value: s, label: `${t(`oldCrm.status.${s}`)} ${totals[s]}` })),
]
const statusText = (s: ImportStatus) => (result.value ? t(`oldCrm.statusDone.${s}`) : t(`oldCrm.status.${s}`))
const ready = computed(() => !!preview.value && !stale.value && preview.value.totals.new + preview.value.totals.update > 0)
const STAT_ORDER = ['students_created', 'guardians', 'staff_created', 'groups_created', 'individual_groups', 'memberships', 'rules',
  'lessons_planned', 'lessons_held', 'marks_created', 'payments', 'payments_sum', 'books']
const stats = computed(() => {
  const s = view.value?.stats ?? {}
  return STAT_ORDER.filter((k) => s[k]).map((k) => ({ k, v: s[k] ?? 0 }))
})
const LINKS = [
  ['students', '/students'], ['groups', '/groups'], ['schedule', '/schedule'], ['attendance', '/attendance'], ['payments', '/payments'],
  ['staff', '/settings/staff'], ['books', '/books'],
] as const
</script>

<template>
  <nav class="crumbs" :aria-label="t('common.breadcrumbs')"><RouterLink to="/settings/general">{{ t('nav.settingsPage') }}</RouterLink> / <span>{{ t('oldCrm.title') }}</span></nav>
  <div class="ph">
    <div><h1>{{ t('oldCrm.title') }}</h1><p>{{ t('oldCrm.subtitle') }}</p></div>
  </div>

  <ol class="import-steps">
    <li :class="{ ok: picked.length > 0 }"><b>1</b>{{ t('oldCrm.step1') }}</li>
    <li :class="{ ok: !!preview || !!result }"><b>2</b>{{ t('oldCrm.step2') }}</li>
    <li :class="{ ok: !!result }"><b>3</b>{{ t('oldCrm.step3') }}</li>
  </ol>

  <template v-if="!result">
    <UiCard>
      <label
        class="drop"
        :class="{ over: dragging }"
        @dragover.prevent="dragging = true"
        @dragleave="dragging = false"
        @drop.prevent="onDrop"
      >
        <input ref="input" type="file" multiple accept=".xlsx,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv" class="sr" data-testid="oc-input" @change="add(($event.target as HTMLInputElement).files)" />
        <UiIcon name="file" :size="24" />
        <b>{{ t('oldCrm.drop') }}</b>
        <span class="muted">{{ t('oldCrm.dropHint', { mb: MAX_MB }) }}</span>
      </label>

      <ul v-if="picked.length" class="oc-files" :aria-label="t('oldCrm.files')">
        <li v-for="(p, i) in picked" :key="p.file.name" class="oc-file">
          <UiIcon name="file" :size="20" class="oc-file-ico" />
          <div class="oc-file-main">
            <b class="oc-name">{{ p.file.name }}</b>
            <span class="muted num">{{ size(p.file.size) }}</span>
            <template v-if="fileResult(i) && !stale">
              <UiChip v-if="fileResult(i)!.error" tone="red" icon="alert" small>{{ fileResult(i)!.error }}</UiChip>
              <UiChip v-else-if="fileResult(i)!.detected" tone="ok" icon="ok" small>{{ t('oldCrm.detected', { kind: kindLabel(fileResult(i)!.detected) }) }}</UiChip>
              <UiChip v-else tone="warn" icon="alert" small>{{ t('oldCrm.notDetected') }}</UiChip>
            </template>
          </div>
          <div class="oc-file-acts">
            <UiSelect v-model="p.kind" :options="kindOptions" :label="`${t('oldCrm.override')}: ${p.file.name}`" />
            <button type="button" class="iconbtn" :aria-label="t('oldCrm.remove')" :title="t('oldCrm.remove')" @click="removeAt(i)"><UiIcon name="x" :size="18" /></button>
          </div>
        </li>
      </ul>

      <div v-if="picked.length" class="oc-opts">
        <div class="oc-opt">
          <b>{{ t('oldCrm.defaultBranch') }}</b>
        </div>
        <UiSelect v-model="branchId" :options="branchOptions" :label="t('oldCrm.defaultBranch')" />
      </div>

      <div v-if="picked.length" class="oc-actions">
        <span v-if="busy" class="muted oc-busy" role="status">{{ busy === 'commit' ? t('oldCrm.committing') : t('oldCrm.checking') }}</span>
        <span class="sp" />
        <UiButton variant="ghost" :disabled="!!busy" @click="reset">{{ t('common.reset') }}</UiButton>
        <UiButton :variant="preview && !stale ? 'default' : 'navy'" icon="check" :loading="busy === 'check'" :disabled="!!busy" data-testid="oc-check" @click="run(false)">
          {{ preview ? t('oldCrm.recheck') : t('oldCrm.check') }}
        </UiButton>
        <UiButton variant="primary" icon="ok" :loading="busy === 'commit'" :disabled="!ready || !!busy" data-testid="oc-commit" @click="run(true)">{{ t('oldCrm.commit') }}</UiButton>
      </div>
      <p v-if="error" class="form-err" role="alert" style="margin-top: 12px">{{ error }}</p>
    </UiCard>
    <div v-if="stale" class="alert" style="margin-top: 16px"><UiIcon name="alert" /><span>{{ t('oldCrm.stale') }}</span></div>
  </template>

  <template v-if="view">
    <div class="oc-summary" :class="{ done: !!result }" data-testid="oc-summary">
      <div class="oc-sum-h">
        <UiIcon :name="result ? 'ok' : 'eye'" :size="20" />
        <h2>{{ result ? t('oldCrm.done') : t('oldCrm.step2') }}</h2>
        <span class="sp" />
        <UiChip v-for="s in STATUSES" :key="s" :tone="TONE[s]">{{ statusText(s) }}: <b class="num">{{ view.totals[s] }}</b></UiChip>
      </div>
      <div v-if="stats.length" class="oc-stats">
        <div v-for="s in stats" :key="s.k" class="oc-stat"><span class="num">{{ statValue(s.k, s.v) }}</span><small>{{ statLabel(s.k) }}</small></div>
      </div>
      <div v-if="!result && view.totals.error" class="alert red" style="margin: 12px 0 0"><UiIcon name="alert" /><span>{{ t('oldCrm.errorsWarn', { n: view.totals.error }) }}</span></div>
      <template v-if="result">
        <div class="oc-links">
          <UiButton v-for="[k, to] in LINKS" :key="k" size="sm" :to="to" icon-end="arrow">{{ t(`oldCrm.links.${k}`) }}</UiButton>
          <span class="sp" />
          <UiButton size="sm" variant="ghost" @click="reset">{{ t('oldCrm.again') }}</UiButton>
        </div>
      </template>
    </div>

    <UiCard v-for="sec in sections" :key="sec.id" class="oc-sec" flush>
      <template #header>
        <div class="oc-sec-h">
          <h3>{{ sec.title }}</h3>
          <span v-if="sec.sub" class="muted oc-sub">{{ sec.sub }}</span>
        </div>
      </template>
      <template #actions>
        <span v-if="sec.ms" class="muted num oc-ms">{{ t('oldCrm.took', { s: (sec.ms / 1000).toFixed(1) }) }}</span>
      </template>
      <div class="oc-sec-b">
        <p v-if="sec.error" class="form-err" role="alert">{{ sec.error }}</p>
        <template v-else>
          <div class="oc-sec-tools">
            <UiSegmented v-if="sec.rows.length" :model-value="filter[sec.id] ?? 'all'" :options="filterOptions(sec.totals, sec.rows.length)" :label="t('oldCrm.status.all')" size="sm" @update:model-value="(v: ImportStatus | 'all') => { filter[sec.id] = v; shown[sec.id] = PAGE }" />
            <span v-for="(v, k) in sec.stats" :key="k" class="chip">{{ statLabel(String(k)) }}: <b class="num">{{ statValue(String(k), v) }}</b></span>
          </div>
          <UiEmptyState v-if="!sec.rows.length" icon="file" :title="t('oldCrm.noRows')" />
          <p v-else-if="!rowsOf(sec.id, sec.rows).length" class="muted">{{ t('oldCrm.noneWithStatus') }}</p>
          <ul v-else class="oc-rows">
            <li v-for="(r, i) in rowsOf(sec.id, sec.rows).slice(0, shown[sec.id] ?? PAGE)" :key="`${r.row}-${i}`" class="oc-row" :class="r.status">
              <span v-if="r.row" class="chip num oc-rn">{{ t('oldCrm.row', { n: r.row }) }}</span>
              <UiChip :tone="TONE[r.status]" small>{{ statusText(r.status) }}</UiChip>
              <div class="oc-row-t"><b>{{ r.label }}</b><span v-if="r.reason">{{ r.reason }}</span></div>
            </li>
          </ul>
          <div v-if="rowsOf(sec.id, sec.rows).length > (shown[sec.id] ?? PAGE)" class="oc-more">
            <UiButton size="sm" variant="ghost" @click="shown[sec.id] = (shown[sec.id] ?? PAGE) + 200">
              {{ t('oldCrm.showMore', { n: Math.min(200, rowsOf(sec.id, sec.rows).length - (shown[sec.id] ?? PAGE)) }) }}
            </UiButton>
          </div>
        </template>
      </div>
    </UiCard>
  </template>

  <OldCrmAnnulCard />
</template>
