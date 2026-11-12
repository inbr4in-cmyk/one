<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiCard, UiEmptyState, UiField, UiInput, UiModal, UiPrompt, UiSelect, UiSkeleton, UiTabs } from '@/components/ui'
import { financeApi, type ExpenseCategory } from '@/api/finance'
import { orgApi, type Branch, type Level, type LevelIn, type Room } from '@/api/org'
import { crmApi, sourcesApi, type Pipeline, type Stage } from '@/api/crm'
import { useSourcesStore } from '@/stores/sources'
import { packagesApi, type SubscriptionPackage } from '@/api/payments'
import { useAuthStore } from '@/stores/auth'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import { money } from '@/utils/dates'
import { apiErr } from '@/utils/err'
import type { Locale } from '@/i18n'

/** Reference lists the school edits itself: expense items, levels with the lesson price, lead funnel columns.
 *  Nothing is deleted: removed items go to the archive so past payments, expenses and leads keep their names. */
type Tab = 'expenses' | 'levels' | 'packages' | 'sources' | 'rooms' | 'stages'
const { t, locale } = useI18n()
const auth = useAuthStore()
const refs = useRefsStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)

const tabs = computed(() => [
  ...(auth.can('finance.edit') ? [{ value: 'expenses' as Tab, label: t('dict.tab.expenses') }] : []),
  ...(auth.can('settings.edit') ? [{ value: 'levels' as Tab, label: t('dict.tab.levels') }, { value: 'packages' as Tab, label: t('dict.tab.packages') }, { value: 'stages' as Tab, label: t('dict.tab.stages') }, { value: 'sources' as Tab, label: t('dict.tab.sources') }] : []),
  ...(auth.can('branches.edit') ? [{ value: 'rooms' as Tab, label: t('dict.tab.rooms') }] : []),
])
const tab = ref<Tab>(tabs.value[0]?.value ?? 'levels')
const busy = ref(false)
const confirm = ref<{ kind: Tab; id: number; name: string; code?: string } | null>(null)

/* ---------- expense items ---------- */
const cats = ref<ExpenseCategory[] | null>(null)
const catNew = ref('')
const catEdit = reactive<{ id: number | null; name: string }>({ id: null, name: '' })
async function loadCats() {
  cats.value = await financeApi.categories().catch(() => [])
}
async function addCat() {
  const name = catNew.value.trim()
  if (name.length < 2) return toast.error(t('dict.nameMin'))
  busy.value = true
  try {
    cats.value = [...(cats.value ?? []), await financeApi.createCategory({ name })]
    catNew.value = ''
    toast.ok(t('dict.added'))
  } catch (e) {
    toast.error(apiErr(e) ?? t('errors.generic'))
  } finally {
    busy.value = false
  }
}
async function saveCat() {
  if (catEdit.id === null || catEdit.name.trim().length < 2) return
  busy.value = true
  try {
    const c = await financeApi.renameCategory(catEdit.id, catEdit.name.trim())
    cats.value = (cats.value ?? []).map((x) => (x.id === c.id ? c : x))
    catEdit.id = null
    toast.ok(t('dict.saved'))
  } finally {
    busy.value = false
  }
}

/* ---------- «Откуда узнал» (lead sources) ---------- */
const sources = useSourcesStore()
const srcNew = ref('')
const srcEdit = reactive<{ code: string | null; name: string }>({ code: null, name: '' })
const srcShown = computed(() => sources.items.filter((x) => !x.hidden && x.code !== 'import'))
async function addSrc() {
  const name = srcNew.value.trim()
  if (name.length < 2) return toast.error(t('dict.nameMin'))
  busy.value = true
  try {
    await sourcesApi.add(name)
    srcNew.value = ''
    toast.ok(t('dict.added'))
    await sources.load(true)
  } finally {
    busy.value = false
  }
}
async function saveSrc() {
  if (!srcEdit.code || srcEdit.name.trim().length < 2) return
  busy.value = true
  try {
    await sourcesApi.rename(srcEdit.code, srcEdit.name.trim())
    srcEdit.code = null
    toast.ok(t('dict.saved'))
    await sources.load(true)
  } finally {
    busy.value = false
  }
}

/* ---------- levels and prices ---------- */
const levelModal = ref(false)
const levelId = ref<number | null>(null)
const lf = reactive({ name: '', lesson_price: '', track: 'adults' as Level['track'], duration_months: '3', color: '#1A6FD1', next_level_id: 0 })
const trackOptions = computed(() => (['adults', 'kids', 'exam'] as const).map((v) => ({ value: v, label: t(`dict.track.${v}`) })))
const nextOptions = computed(() => [{ value: 0, label: '—' }, ...refs.levels.filter((l) => l.id !== levelId.value).map((l) => ({ value: l.id, label: l.name }))])
function openLevel(l: Level | null) {
  levelId.value = l?.id ?? null
  Object.assign(lf, l
    ? { name: l.name, lesson_price: String(l.lesson_price), track: l.track, duration_months: String(l.duration_months), color: l.color, next_level_id: l.next_level_id ?? 0 }
    : { name: '', lesson_price: '', track: 'adults', duration_months: '3', color: '#1A6FD1', next_level_id: 0 })
  levelModal.value = true
}
async function saveLevel() {
  const price = Math.round(Number(lf.lesson_price))
  if (lf.name.trim().length < 2 || !(price >= 0) || lf.lesson_price === '') return toast.error(t('dict.levelInvalid'))
  const cur = levelId.value ? refs.levels.find((l) => l.id === levelId.value) : null
  const body: LevelIn = {
    name: lf.name.trim(), code: cur?.code ?? null, color: lf.color, lesson_price: price, track: lf.track,
    duration_months: Math.max(1, Math.round(Number(lf.duration_months) || 1)), next_level_id: lf.next_level_id || null,
    order: cur?.order ?? Math.max(0, ...refs.levels.map((l) => l.order)) + 1,
  }
  busy.value = true
  try {
    const saved = levelId.value ? await orgApi.updateLevel(levelId.value, body) : await orgApi.createLevel(body)
    refs.levels = levelId.value ? refs.levels.map((l) => (l.id === saved.id ? saved : l)) : [...refs.levels, saved]
    levelModal.value = false
    toast.ok(t('dict.saved'))
  } finally {
    busy.value = false
  }
}

/* ---------- branches and rooms ---------- */
const roomsBy = ref<Record<number, Room[]> | null>(null)
async function loadRooms() {
  const entries = await Promise.all(refs.branches.map(async (b) => [b.id, await orgApi.rooms(b.id).catch(() => [])] as const))
  roomsBy.value = Object.fromEntries(entries)
  refs.rooms = { ...refs.rooms, ...roomsBy.value }
}
const roomModal = ref(false)
const roomId = ref<number | null>(null)
const roomBranch = ref(0)
const rf = reactive({ name: '', capacity: '12', equipment: '', status: 'active' as Room['status'] })
const statusOptions = computed(() => (['active', 'repair'] as const).map((v) => ({ value: v, label: t(`dict.roomStatus.${v}`) })))
function openRoom(branchId: number, r: Room | null) {
  roomBranch.value = branchId
  roomId.value = r?.id ?? null
  Object.assign(rf, r ? { name: r.name, capacity: String(r.capacity), equipment: r.equipment ?? '', status: r.status } : { name: '', capacity: '12', equipment: '', status: 'active' })
  roomModal.value = true
}
async function saveRoom() {
  const body = { name: rf.name.trim(), capacity: Math.round(Number(rf.capacity)), equipment: rf.equipment.trim() || null, status: rf.status }
  if (!body.name || !(body.capacity >= 1)) return toast.error(t('dict.roomInvalid'))
  busy.value = true
  try {
    if (roomId.value) await orgApi.updateRoom(roomId.value, body)
    else await orgApi.createRoom(roomBranch.value, body)
    roomModal.value = false
    toast.ok(t('dict.saved'))
    await loadRooms()
  } finally {
    busy.value = false
  }
}
const branchModal = ref(false)
const branchId = ref<number | null>(null)
const bf = reactive({ name: '', address: '', phone: '', hours: '' })
function openBranch(b: Branch | null) {
  branchId.value = b?.id ?? null
  Object.assign(bf, { name: b?.name ?? '', address: b?.address ?? '', phone: b?.phone ?? '', hours: b?.hours ?? '' })
  branchModal.value = true
}
async function saveBranch() {
  if (bf.name.trim().length < 2) return toast.error(t('dict.nameMin'))
  const cur = branchId.value ? refs.branches.find((b) => b.id === branchId.value) : null
  const body = { name: bf.name.trim(), address: bf.address.trim() || null, phone: bf.phone.trim() || null, hours: bf.hours.trim() || null, admin_id: cur?.admin_id ?? null }
  busy.value = true
  try {
    const saved = branchId.value ? await orgApi.updateBranch(branchId.value, body) : await orgApi.createBranch(body)
    refs.branches = branchId.value ? refs.branches.map((b) => (b.id === saved.id ? saved : b)) : [...refs.branches, saved]
    branchModal.value = false
    toast.ok(t('dict.saved'))
    await loadRooms()
  } finally {
    busy.value = false
  }
}

/* ---------- subscriptions (абонементы) ---------- */
const packages = ref<SubscriptionPackage[] | null>(null)
async function loadPackages() {
  packages.value = await packagesApi.list().catch(() => [])
}
const pkgModal = ref(false)
const pkgId = ref<number | null>(null)
const pf = reactive({ name: '', months: '3', price: '', lessons: '36', lessonsTouched: false })
function openPkg(p: SubscriptionPackage | null) {
  pkgId.value = p?.id ?? null
  Object.assign(pf, p
    ? { name: p.name, months: String(p.months), price: String(p.price), lessons: String(p.lessons), lessonsTouched: true }
    : { name: '', months: '3', price: '', lessons: '36', lessonsTouched: false })
  pkgModal.value = true
}
// 3 lessons a week ≈ 12 a month: suggested until the lessons field is edited by hand
watch(() => pf.months, (m) => {
  if (!pf.lessonsTouched) pf.lessons = String(Math.max(1, Math.round(Number(m) || 1)) * 12)
})
const pkgPerLesson = computed(() => {
  const price = Number(pf.price)
  const n = Number(pf.lessons)
  return price > 0 && n > 0 ? money(Math.floor(price / n), loc.value) : '—'
})
async function savePkg() {
  const body = { name: pf.name.trim(), months: Math.round(Number(pf.months)), price: Math.round(Number(pf.price)), lessons: Math.round(Number(pf.lessons)) }
  if (body.name.length < 2 || !(body.months >= 1) || !(body.price >= 1) || !(body.lessons >= 1)) return toast.error(t('dict.pkgInvalid'))
  busy.value = true
  try {
    if (pkgId.value) await packagesApi.update(pkgId.value, body)
    else await packagesApi.create(body)
    pkgModal.value = false
    toast.ok(t('dict.saved'))
    await loadPackages()
  } finally {
    busy.value = false
  }
}

/* ---------- lead funnel columns ---------- */
const pipelines = ref<Pipeline[] | null>(null)
const pipelineId = ref(0)
const pipeline = computed(() => pipelines.value?.find((p) => p.id === pipelineId.value) ?? null)
const pipelineOptions = computed(() => (pipelines.value ?? []).map((p) => ({ value: p.id, label: p.name })))
const stageModal = ref(false)
const stageId = ref<number | null>(null)
const sf = reactive({ name: '', color: '#5B6782', stale: '' })
async function loadPipelines() {
  pipelines.value = await crmApi.pipelines().catch(() => [])
  if (!pipeline.value) pipelineId.value = pipelines.value[0]?.id ?? 0
}
function openStage(s: Stage | null) {
  stageId.value = s?.id ?? null
  Object.assign(sf, { name: s?.name ?? '', color: s?.color ?? '#5B6782', stale: s?.stale_after_hours ? String(s.stale_after_hours) : '' })
  stageModal.value = true
}
async function saveStage() {
  if (!pipeline.value || !sf.name.trim()) return toast.error(t('dict.nameMin'))
  const body = { name: sf.name.trim(), color: sf.color, stale_after_hours: sf.stale ? Math.max(1, Math.round(Number(sf.stale))) : null }
  busy.value = true
  try {
    if (stageId.value) await crmApi.editStage(stageId.value, body)
    else await crmApi.addStage(pipeline.value.id, body)
    await loadPipelines()
    stageModal.value = false
    toast.ok(t('dict.saved'))
  } finally {
    busy.value = false
  }
}
async function move(i: number, dir: -1 | 1) {
  const p = pipeline.value
  if (!p) return
  const ids = p.stages.map((s) => s.id)
  const j = i + dir
  if (j < 0 || j >= ids.length) return
  const a = ids[i] as number
  ids[i] = ids[j] as number
  ids[j] = a
  const stages = await crmApi.orderStages(p.id, ids)
  p.stages = stages
}
const isFinal = (s: Stage) => s.is_won || s.is_lost

/* ---------- archive ---------- */
async function doArchive() {
  const c = confirm.value
  if (!c) return
  busy.value = true
  try {
    if (c.kind === 'expenses') {
      await financeApi.archiveCategory(c.id)
      cats.value = (cats.value ?? []).filter((x) => x.id !== c.id)
    } else if (c.kind === 'levels') {
      await orgApi.archiveLevel(c.id)
      refs.levels = refs.levels.filter((l) => l.id !== c.id)
    } else if (c.kind === 'packages') {
      await packagesApi.archive(c.id)
      packages.value = (packages.value ?? []).filter((x) => x.id !== c.id)
    } else if (c.kind === 'sources' && c.code) {
      await sourcesApi.archive(c.code)
      await sources.load(true)
    } else if (c.kind === 'rooms') {
      await orgApi.archiveRoom(c.id)
      await loadRooms()
    } else {
      await crmApi.archiveStage(c.id)
      await loadPipelines()
    }
    toast.ok(t('dict.archived'))
    confirm.value = null
  } finally {
    busy.value = false
  }
}

function loadTab() {
  if (tab.value === 'expenses' && !cats.value) loadCats()
  if (tab.value === 'stages' && !pipelines.value) loadPipelines()
  if (tab.value === 'packages' && !packages.value) loadPackages()
  if (tab.value === 'sources') void sources.load(true)
  if (tab.value === 'rooms' && !roomsBy.value) loadRooms()
}
onMounted(() => {
  refs.load()
  loadTab()
})
watch(tab, loadTab)
</script>

<template>
  <div class="ph">
    <div><h1>{{ t('nav.dictionaries') }}</h1><p>{{ t('dict.subtitle') }}</p></div>
    <span class="sp" />
    <UiButton v-if="tab === 'levels'" variant="primary" icon="plus" @click="openLevel(null)">{{ t('dict.addLevel') }}</UiButton>
    <UiButton v-if="tab === 'rooms' && auth.can('branches.create', 'network')" variant="primary" icon="plus" @click="openBranch(null)">{{ t('dict.addBranch') }}</UiButton>
    <UiButton v-if="tab === 'packages'" variant="primary" icon="plus" @click="openPkg(null)">{{ t('dict.addPkg') }}</UiButton>
    <UiButton v-if="tab === 'stages' && pipeline" variant="primary" icon="plus" @click="openStage(null)">{{ t('dict.addStage') }}</UiButton>
  </div>
  <div class="toolbar">
    <UiTabs v-model="tab" :items="tabs" :label="t('nav.dictionaries')" />
    <UiSelect v-if="tab === 'stages' && pipelineOptions.length > 1" v-model="pipelineId" :options="pipelineOptions" :label="t('dict.pipeline')" />
  </div>

  <!-- expense items -->
  <UiCard v-if="tab === 'expenses'">
    <form class="add-row" @submit.prevent="addCat">
      <UiInput v-model="catNew" :label="t('dict.newExpense')" :placeholder="t('fin.catNamePh')" :maxlength="120" />
      <UiButton type="submit" variant="navy" icon="plus" :loading="busy">{{ t('common.add') }}</UiButton>
    </form>
    <UiSkeleton v-if="!cats" :lines="5" />
    <UiEmptyState v-else-if="!cats.length" icon="finance" :title="t('dict.empty')" />
    <div v-for="c in cats ?? []" :key="c.id" class="list-row">
      <template v-if="catEdit.id === c.id">
        <form class="grow edit-row" @submit.prevent="saveCat">
          <UiInput v-model="catEdit.name" :label="t('dict.name')" :maxlength="120" autofocus />
          <UiButton type="submit" size="sm" variant="navy" :loading="busy">{{ t('common.save') }}</UiButton>
          <UiButton size="sm" @click="catEdit.id = null">{{ t('common.cancel') }}</UiButton>
        </form>
      </template>
      <template v-else>
        <div class="grow"><b>{{ c.name }}</b></div>
        <UiButton size="sm" variant="ghost" icon="edit" :aria-label="`${t('common.edit')}: ${c.name}`" @click="catEdit.id = c.id; catEdit.name = c.name" />
        <UiButton size="sm" variant="ghost" icon="archive" :aria-label="`${t('dict.archive')}: ${c.name}`" @click="confirm = { kind: 'expenses', id: c.id, name: c.name }" />
      </template>
    </div>
  </UiCard>

  <!-- «Откуда узнал» -->
  <UiCard v-else-if="tab === 'sources'">
    <form class="add-row" @submit.prevent="addSrc">
      <UiInput v-model="srcNew" :label="t('dict.newSource')" :placeholder="t('dict.sourcePh')" :maxlength="60" />
      <UiButton type="submit" variant="navy" icon="plus" :loading="busy">{{ t('common.add') }}</UiButton>
    </form>
    <div v-for="x in srcShown" :key="x.code" class="list-row">
      <template v-if="srcEdit.code === x.code">
        <form class="grow edit-row" @submit.prevent="saveSrc">
          <UiInput v-model="srcEdit.name" :label="t('dict.name')" :maxlength="60" autofocus />
          <UiButton type="submit" size="sm" variant="navy" :loading="busy">{{ t('common.save') }}</UiButton>
          <UiButton size="sm" @click="srcEdit.code = null">{{ t('common.cancel') }}</UiButton>
        </form>
      </template>
      <template v-else>
        <div class="grow"><b>{{ x.name }}</b><span v-if="x.system">{{ t('dict.systemSource') }}</span></div>
        <UiButton size="sm" variant="ghost" icon="edit" :aria-label="`${t('common.edit')}: ${x.name}`" @click="srcEdit.code = x.code; srcEdit.name = x.name" />
        <UiButton v-if="!x.system" size="sm" variant="ghost" icon="archive" :aria-label="`${t('dict.archive')}: ${x.name}`" @click="confirm = { kind: 'sources', id: 0, code: x.code, name: x.name }" />
      </template>
    </div>
  </UiCard>

  <!-- levels and prices -->
  <UiCard v-else-if="tab === 'levels'" flush>
    <UiEmptyState v-if="!refs.levels.length" icon="level" :title="t('dict.empty')" />
    <div v-else class="scroll-x">
      <table class="tbl" style="min-width: 560px">
        <thead><tr><th>{{ t('dict.level') }}</th><th>{{ t('dict.trackLabel') }}</th><th class="r">{{ t('dict.price') }}</th><th class="r">{{ t('dict.months') }}</th><th class="r"><span class="sr">{{ t('books.actions') }}</span></th></tr></thead>
        <tbody>
          <tr v-for="l in refs.levels" :key="l.id">
            <td><span class="dot" :style="{ background: l.color }" /> <b>{{ l.name }}</b></td>
            <td>{{ t(`dict.track.${l.track}`) }}</td>
            <td class="r num">{{ money(l.lesson_price, loc) }}</td>
            <td class="r num">{{ l.duration_months }}</td>
            <td class="r">
              <div class="row-acts nowrap">
                <UiButton size="sm" variant="ghost" icon="edit" :aria-label="`${t('common.edit')}: ${l.name}`" @click="openLevel(l)" />
                <UiButton size="sm" variant="ghost" icon="archive" :aria-label="`${t('dict.archive')}: ${l.name}`" @click="confirm = { kind: 'levels', id: l.id, name: l.name }" />
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </UiCard>

  <!-- branches and rooms -->
  <template v-else-if="tab === 'rooms'">
    <UiCard v-if="!roomsBy"><UiSkeleton :lines="5" /></UiCard>
    <UiCard v-for="b in roomsBy ? refs.branches : []" :key="b.id" flush class="br-card">
      <div class="br-head">
        <div class="grow"><b>{{ b.name }}</b><span class="muted">{{ [b.address, b.phone, b.hours].filter(Boolean).join(' · ') || t('dict.noAddress') }}</span></div>
        <UiButton size="sm" variant="ghost" icon="edit" @click="openBranch(b)">{{ t('dict.editBranch') }}</UiButton>
        <UiButton size="sm" icon="plus" @click="openRoom(b.id, null)">{{ t('dict.addRoom') }}</UiButton>
      </div>
      <p v-if="!(roomsBy?.[b.id] ?? []).length" class="muted card-pad m0">{{ t('dict.noRooms') }}</p>
      <div v-else class="scroll-x">
        <table class="tbl" style="min-width: 520px">
          <thead><tr><th>{{ t('dict.room') }}</th><th class="r">{{ t('dict.capacity') }}</th><th>{{ t('dict.equipment') }}</th><th>{{ t('dict.status') }}</th><th class="r"><span class="sr">{{ t('books.actions') }}</span></th></tr></thead>
          <tbody>
            <tr v-for="r in roomsBy?.[b.id] ?? []" :key="r.id">
              <td><b>{{ r.name }}</b></td>
              <td class="r num">{{ r.capacity }}</td>
              <td class="muted">{{ r.equipment || '—' }}</td>
              <td><span class="chip xs" :class="{ red: r.status === 'repair' }">{{ t(`dict.roomStatus.${r.status}`) }}</span></td>
              <td class="r">
                <div class="row-acts nowrap">
                  <UiButton size="sm" variant="ghost" icon="edit" :aria-label="`${t('common.edit')}: ${r.name}`" @click="openRoom(b.id, r)" />
                  <UiButton size="sm" variant="ghost" icon="archive" :aria-label="`${t('dict.archive')}: ${r.name}`" @click="confirm = { kind: 'rooms', id: r.id, name: r.name }" />
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </UiCard>
  </template>

  <!-- subscriptions -->
  <UiCard v-else-if="tab === 'packages'" flush>
    <div v-if="!packages" class="card-pad"><UiSkeleton :lines="4" /></div>
    <UiEmptyState v-else-if="!packages.length" icon="wallet" :title="t('dict.pkgEmpty')" :text="t('dict.pkgEmptyText')" />
    <div v-else class="scroll-x">
      <table class="tbl" style="min-width: 560px">
        <thead><tr><th>{{ t('dict.pkgName') }}</th><th class="r">{{ t('dict.months') }}</th><th class="r">{{ t('dict.pkgLessons') }}</th><th class="r">{{ t('dict.pkgPrice') }}</th><th class="r">{{ t('dict.pkgPerLesson') }}</th><th class="r"><span class="sr">{{ t('books.actions') }}</span></th></tr></thead>
        <tbody>
          <tr v-for="p in packages" :key="p.id">
            <td><b>{{ p.name }}</b></td>
            <td class="r num">{{ p.months }}</td>
            <td class="r num">{{ p.lessons }}</td>
            <td class="r num"><b>{{ money(p.price, loc) }}</b></td>
            <td class="r num muted">{{ money(Math.floor(p.price / p.lessons), loc) }}</td>
            <td class="r">
              <div class="row-acts nowrap">
                <UiButton size="sm" variant="ghost" icon="edit" :aria-label="`${t('common.edit')}: ${p.name}`" @click="openPkg(p)" />
                <UiButton size="sm" variant="ghost" icon="archive" :aria-label="`${t('dict.archive')}: ${p.name}`" @click="confirm = { kind: 'packages', id: p.id, name: p.name }" />
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </UiCard>

  <!-- lead funnel columns -->
  <UiCard v-else-if="tab === 'stages'">
    <UiSkeleton v-if="!pipelines" :lines="6" />
    <template v-else-if="pipeline">
      <div v-for="(s, i) in pipeline.stages" :key="s.id" class="list-row">
        <span class="dot lg" :style="{ background: s.color }" />
        <div class="grow">
          <b>{{ s.name }}</b>
          <span>
            <template v-if="s.system">{{ t('dict.systemStage') }}</template>
            <template v-if="s.stale_after_hours"> · {{ t('dict.staleAfter', { n: s.stale_after_hours }) }}</template>
          </span>
        </div>
        <div class="row-acts nowrap">
          <UiButton size="sm" variant="ghost" icon="up" :disabled="i === 0 || isFinal(s)" :aria-label="t('dict.up')" @click="move(i, -1)" />
          <UiButton size="sm" variant="ghost" icon="down" :disabled="i === pipeline.stages.length - 1 || isFinal(s) || isFinal(pipeline.stages[i + 1]!)" :aria-label="t('dict.down')" @click="move(i, 1)" />
          <UiButton size="sm" variant="ghost" icon="edit" :aria-label="`${t('common.edit')}: ${s.name}`" @click="openStage(s)" />
          <UiButton v-if="!s.system" size="sm" variant="ghost" icon="archive" :aria-label="`${t('dict.archive')}: ${s.name}`" @click="confirm = { kind: 'stages', id: s.id, name: s.name }" />
        </div>
      </div>
    </template>
  </UiCard>

  <UiModal v-model:open="roomModal" :title="roomId ? t('dict.editRoom') : t('dict.addRoom')">
    <form id="room-form" class="stack" @submit.prevent="saveRoom">
      <div class="form-2">
        <UiInput v-model="rf.name" :label="t('dict.room')" :placeholder="t('dict.roomPh')" :maxlength="64" autofocus />
        <UiInput v-model="rf.capacity" type="number" inputmode="numeric" :min="1" :max="200" :label="t('dict.capacity')" />
      </div>
      <UiInput v-model="rf.equipment" :label="t('dict.equipment')" :placeholder="t('dict.equipmentPh')" :maxlength="255" />
      <UiField :label="t('dict.status')"><UiSelect v-model="rf.status" :options="statusOptions" :label="t('dict.status')" block /></UiField>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="navy" type="submit" form="room-form" :loading="busy">{{ t('common.save') }}</UiButton>
    </template>
  </UiModal>

  <UiModal v-model:open="branchModal" :title="branchId ? t('dict.editBranch') : t('dict.addBranch')">
    <form id="branch-form" class="stack" @submit.prevent="saveBranch">
      <UiInput v-model="bf.name" :label="t('dict.branchName')" :maxlength="120" autofocus />
      <UiInput v-model="bf.address" :label="t('dict.address')" :maxlength="255" />
      <div class="form-2">
        <UiInput v-model="bf.phone" :label="t('dict.phone')" :maxlength="32" />
        <UiInput v-model="bf.hours" :label="t('dict.hours')" :placeholder="t('dict.hoursPh')" :maxlength="255" />
      </div>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="navy" type="submit" form="branch-form" :loading="busy">{{ t('common.save') }}</UiButton>
    </template>
  </UiModal>

  <UiModal v-model:open="pkgModal" :title="pkgId ? t('dict.editPkg') : t('dict.addPkg')">
    <form id="pkg-form" class="stack" @submit.prevent="savePkg">
      <UiInput v-model="pf.name" :label="t('dict.pkgName')" :placeholder="t('dict.pkgPh')" :maxlength="120" autofocus />
      <div class="form-2">
        <UiInput v-model="pf.months" type="number" inputmode="numeric" :min="1" :max="36" :label="t('dict.months')" />
        <UiInput v-model="pf.price" type="number" inputmode="numeric" :min="1" :label="t('dict.pkgPrice')" />
      </div>
      <UiInput v-model="pf.lessons" type="number" inputmode="numeric" :min="1" :label="t('dict.pkgLessons')"
        :hint="t('dict.pkgLessonsHint', { price: pkgPerLesson })" @input="pf.lessonsTouched = true" />
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="navy" type="submit" form="pkg-form" :loading="busy">{{ t('common.save') }}</UiButton>
    </template>
  </UiModal>

  <UiModal v-model:open="levelModal" :title="levelId ? t('dict.editLevel') : t('dict.addLevel')">
    <form id="lvl-form" class="stack" @submit.prevent="saveLevel">
      <UiInput v-model="lf.name" :label="t('dict.levelName')" :placeholder="t('dict.levelPh')" :maxlength="80" autofocus />
      <div class="form-2">
        <UiInput v-model="lf.lesson_price" type="number" inputmode="numeric" :min="0" :label="t('dict.price')" />
        <UiInput v-model="lf.duration_months" type="number" inputmode="numeric" :min="1" :label="t('dict.months')" />
      </div>
      <div class="form-2">
        <UiField :label="t('dict.trackLabel')"><UiSelect v-model="lf.track" :options="trackOptions" :label="t('dict.trackLabel')" block /></UiField>
        <UiField :label="t('dict.next')"><UiSelect v-model="lf.next_level_id" :options="nextOptions" :label="t('dict.next')" block /></UiField>
      </div>
      <label class="color-row"><input v-model="lf.color" type="color" /> {{ t('dict.color') }}</label>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="navy" type="submit" form="lvl-form" :loading="busy">{{ t('common.save') }}</UiButton>
    </template>
  </UiModal>

  <UiModal v-model:open="stageModal" :title="stageId ? t('dict.editStage') : t('dict.addStage')">
    <form id="stg-form" class="stack" @submit.prevent="saveStage">
      <UiInput v-model="sf.name" :label="t('dict.stageName')" :maxlength="120" autofocus />
      <UiInput v-model="sf.stale" type="number" inputmode="numeric" :min="1" :label="t('dict.stale')" />
      <label class="color-row"><input v-model="sf.color" type="color" /> {{ t('dict.color') }}</label>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="navy" type="submit" form="stg-form" :loading="busy">{{ t('common.save') }}</UiButton>
    </template>
  </UiModal>

  <UiPrompt :open="!!confirm" :title="t('dict.archive')" :text="t('dict.archiveText', { name: confirm?.name ?? '' })" :confirm-label="t('dict.archive')"
    danger :busy="busy" @update:open="(v) => !v && (confirm = null)" @confirm="doArchive" />
</template>

<style scoped>
.add-row { display: flex; gap: 10px; align-items: flex-end; margin-bottom: 12px }
.add-row > :first-child { flex: 1 }
.edit-row { display: flex; gap: 8px; align-items: flex-end }
.edit-row > :first-child { flex: 1 }
.dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; vertical-align: middle }
.dot.lg { width: 14px; height: 14px; flex: none }
.color-row { display: flex; align-items: center; gap: 10px; font-size: 14px }
.color-row input { width: 44px; height: 32px; border: 1px solid var(--line); border-radius: 8px; background: none; padding: 2px }
@media (max-width: 560px) { .add-row, .edit-row { flex-direction: column; align-items: stretch } }
.br-card { margin-bottom: 12px }
.br-head { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; padding: 14px 16px; border-bottom: 1px solid var(--line) }
.br-head .grow { display: grid; gap: 2px }
</style>
