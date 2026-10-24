<script setup lang="ts">
import { useSourceLabel } from '@/composables/useSourceLabel'
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { UiAvatar, UiButton, UiIcon, UiInput, UiPrompt, UiSelect, UiSkeleton, UiTabs } from '@/components/ui'
import LevelTag from '@/components/students/LevelTag.vue'
import LeadCreateDrawer from '@/components/crm/LeadCreateDrawer.vue'
import LeadDrawer from '@/components/crm/LeadDrawer.vue'
import CrmAnalytics from '@/components/crm/CrmAnalytics.vue'
import { crmApi, LEAD_SOURCES, type Board, type Lead, type Pipeline, type Stage } from '@/api/crm'
import { ApiError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { useBranchStore } from '@/stores/branch'
import { useToastStore } from '@/stores/toast'
import { useRealtime } from '@/composables/useRealtime'
import { dayLabel, hm, waitLabel } from '@/utils/dates'
import type { Locale } from '@/i18n'
import { tone } from '@/utils/levels'
import { formatPhone } from '@/utils/phone'

const { t, te, locale } = useI18n()
const srcLabel = useSourceLabel()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const branch = useBranchStore()
const toast = useToastStore()

const pipelines = ref<Pipeline[]>([])
const tab = ref<string>('main')
const board = ref<Board | null>(null)
const loading = ref(true)
const q = ref('')
const source = ref('')
const owner = ref(0)
const waitingOnly = ref(false)
const creating = ref(false)
const openId = ref<number | null>(Number(route.query.lead) || null)
const dragId = ref<number | null>(null)
const dropStage = ref<number | null>(null)
const lostMove = ref<{ lead: Lead; stage: Stage } | null>(null)
const busy = ref(false)
let seq = 0

const tabs = computed(() => [
  ...pipelines.value.map((p) => ({
    value: p.code,
    label: p.code === 'main' ? t('crm.tabSales') : p.code === 'return' ? t('crm.tabReturn') : p.name,
    count: p.code === tab.value ? board.value?.columns.reduce((a, c) => a + (c.stage.is_won || c.stage.is_lost ? 0 : c.total), 0) : undefined,
  })),
  { value: 'analytics', label: t('crm.tabAnalytics') },
])
const sourceOptions = computed(() => [{ value: '', label: t('crm.allSources') }, ...LEAD_SOURCES.map((s) => ({ value: s, label: t(`crm.source.${s}`) }))])
const owners = computed(() => {
  const m = new Map<number, string>()
  board.value?.columns.forEach((c) => c.leads.forEach((l) => l.owner_id && l.owner_name && m.set(l.owner_id, l.owner_name)))
  return [...m]
})
const ownerOptions = computed(() => [{ value: 0, label: t('crm.allOwners') }, ...owners.value.map(([id, name]) => ({ value: id, label: name }))])
const waitingCount = computed(() => board.value?.columns.reduce((a, c) => a + c.leads.filter(isWaiting).length, 0) ?? 0)
const isWaiting = (l: Lead) => l.waiting_min !== null && l.waiting_min > 30
const visible = (leads: Lead[]) => (waitingOnly.value ? leads.filter(isWaiting) : leads)
const stageName = (s: Stage) => (te(`crm.stage.${s.code}`) ? t(`crm.stage.${s.code}`) : s.name)

async function load() {
  if (tab.value === 'analytics') return
  const my = ++seq
  loading.value = !board.value || board.value.pipeline.code !== tab.value
  try {
    const b = await crmApi.board({ pipeline: tab.value, branch_id: branch.filterId, source: source.value || undefined, owner_id: owner.value || null, q: q.value.trim() || undefined })
    if (my === seq) board.value = b
  } catch {
    /* toast */
  } finally {
    if (my === seq) loading.value = false
  }
}
let timer: ReturnType<typeof setTimeout> | undefined
watch(q, () => {
  clearTimeout(timer)
  timer = setTimeout(load, 300)
})
watch([tab, source, owner, () => branch.filterId], load)
watch(openId, (id) => router.replace({ query: { ...route.query, lead: id ?? undefined } }))
onMounted(async () => {
  pipelines.value = await crmApi.pipelines().catch(() => [])
  load()
})
// New DMs create leads and move "waiting" timers.
useRealtime('inbox.message', () => {
  clearTimeout(timer)
  timer = setTimeout(load, 800)
})

/* ---------- drag & drop: optimistic, rolled back on error ---------- */
function findLead(id: number) {
  for (const c of board.value?.columns ?? []) {
    const i = c.leads.findIndex((l) => l.id === id)
    if (i >= 0) return { col: c, i, lead: c.leads[i]! }
  }
  return null
}
function onDragStart(e: DragEvent, l: Lead) {
  dragId.value = l.id
  e.dataTransfer?.setData('text/plain', String(l.id))
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
}
function onDragEnd() {
  dragId.value = dropStage.value = null
}
function canDrop(s: Stage) {
  return !s.is_won && s.code !== 'trial_done'
}
function onDrop(s: Stage) {
  const id = dragId.value
  dropStage.value = dragId.value = null
  if (id === null) return
  const found = findLead(id)
  if (!found || found.lead.stage_id === s.id) return
  if (s.is_won) return toast.error(t('crm.wonAuto'))
  if (s.code === 'trial_done') return toast.error(t('crm.trialDoneAuto'))
  if (s.is_lost) {
    lostMove.value = { lead: found.lead, stage: s }
    return
  }
  move(found.lead, s, null)
}

async function move(lead: Lead, s: Stage, reason: string | null) {
  const b = board.value
  const from = findLead(lead.id)
  const to = b?.columns.find((c) => c.stage.id === s.id)
  if (!b || !from || !to) return
  // Optimistic: move the card now
  from.col.leads.splice(from.i, 1)
  from.col.total--
  const moved = { ...lead, stage_id: s.id, waiting_min: null }
  to.leads.unshift(moved)
  to.total++
  try {
    const fresh = await crmApi.stage(lead.id, s.id, reason, true)
    const i = to.leads.findIndex((l) => l.id === lead.id)
    if (i >= 0) to.leads[i] = fresh
  } catch (e) {
    // Roll back
    const i = to.leads.findIndex((l) => l.id === lead.id)
    if (i >= 0) to.leads.splice(i, 1)
    to.total--
    from.col.leads.splice(from.i, 0, lead)
    from.col.total++
    toast.error(e instanceof ApiError && e.detail ? e.detail : t('crm.moveFailed'))
  }
}
async function confirmLost(reason: string) {
  const m = lostMove.value
  if (!m) return
  lostMove.value = null
  await move(m.lead, m.stage, reason)
}

function onChanged(l: Lead) {
  const found = findLead(l.id)
  if (found && found.lead.stage_id === l.stage_id) found.col.leads[found.i] = l
  else load()
}
function onRemoved(id: number) {
  const found = findLead(id)
  if (found) {
    found.col.leads.splice(found.i, 1)
    found.col.total--
  }
}
const SRC: Record<string, { cls: string; icon: string }> = {
  instagram: { cls: 'ig', icon: 'ig' }, whatsapp: { cls: 'wa', icon: 'wa' }, qr: { cls: 'qr', icon: 'qr' }, qr_test: { cls: 'qr', icon: 'qr' }, site: { cls: 'web', icon: 'globe' },
  referral: { cls: 'ref', icon: 'ref' }, sales: { cls: 'call', icon: 'phone' }, return: { cls: 'call', icon: 'lead-return' },
}
const units = computed(() => ({ m: t('time.min'), h: t('time.h'), d: t('time.d') }))
function onCardKey(e: KeyboardEvent, l: Lead) {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    openId.value = l.id
  }
}
</script>

<template>
  <div class="ph">
    <div><h1>{{ t('crm.title') }}</h1><p>{{ t('crm.subtitle') }}</p></div>
    <span class="sp" />
    <UiButton v-if="auth.can('crm.create')" variant="primary" icon="plus" @click="creating = true">{{ t('crm.newLead') }}</UiButton>
  </div>
  <UiTabs v-model="tab" :items="tabs" :label="t('crm.title')" />

  <CrmAnalytics v-if="tab === 'analytics'" />
  <template v-else>
    <div class="toolbar">
      <UiInput v-model="q" type="search" icon="search" :placeholder="t('crm.searchPh')" class="tb-search" />
      <UiSelect v-model="source" :options="sourceOptions" :label="t('crm.sourceLabel')" />
      <UiSelect v-if="owners.length > 1" v-model="owner" :options="ownerOptions" :label="t('crm.owner')" />
      <button v-if="waitingCount || waitingOnly" type="button" class="tgl danger" :aria-pressed="waitingOnly" @click="waitingOnly = !waitingOnly">
        <UiIcon name="clock" :size="16" />{{ t('crm.waiting', { n: waitingCount }) }}
      </button>
    </div>

    <div class="scroll-x">
      <div v-if="loading" class="kanban"><div v-for="i in 5" :key="i" class="col"><UiSkeleton :lines="5" /></div></div>
      <div v-else-if="board" class="kanban">
        <section
          v-for="c in board.columns" :key="c.stage.id" class="col"
          :class="{ drop: dropStage === c.stage.id && canDrop(c.stage), nodrop: dropStage === c.stage.id && !canDrop(c.stage) }"
          :aria-label="stageName(c.stage)"
          @dragover.prevent="dropStage = c.stage.id" @dragleave="dropStage === c.stage.id && (dropStage = null)" @drop.prevent="onDrop(c.stage)"
        >
          <div class="col-h">
            <span class="st" :style="{ background: tone(c.stage.color) }" /><b>{{ stageName(c.stage) }}</b><span class="c">{{ c.total }}</span><span class="sp" />
            <UiIcon v-if="!canDrop(c.stage)" name="lock" :size="14" class="muted" :title="c.stage.is_won ? t('crm.wonAuto') : t('crm.trialDoneAuto')" />
          </div>
          <TransitionGroup name="fade" tag="div" class="col-b">
            <article
              v-for="l in visible(c.leads)" :key="l.id" class="lead" :class="{ hot: isWaiting(l), dragging: dragId === l.id, star: l.is_hot }"
              :draggable="auth.can('crm.edit')" tabindex="0" role="button" :aria-label="l.full_name"
              @dragstart="onDragStart($event, l)" @dragend="onDragEnd" @click="openId = l.id" @keydown="onCardKey($event, l)"
            >
              <div class="r1">
                <span class="srcico" :class="SRC[l.source]?.cls" :title="srcLabel(l.source)"><svg><use :href="`#i-${SRC[l.source]?.icon ?? 'user'}`" /></svg></span>
                <b>{{ l.full_name }}</b>
                <UiAvatar v-if="l.owner_name" :name="l.owner_name" size="sm" :title="l.owner_name" />
                <span v-else class="chip red xs">{{ t('crm.unassigned') }}</span>
              </div>
              <div class="meta">
                <template v-if="l.lost_reason">{{ t('crm.reason', { r: l.lost_reason }) }}</template>
                <template v-else-if="l.trial_at">{{ t('crm.trialAt', { when: `${dayLabel(l.trial_at, locale as Locale, { day: 'numeric', month: 'short' })}, ${hm(l.trial_at, locale as Locale)}` }) }}</template>
                <template v-else-if="l.phone">{{ formatPhone(l.phone) }}</template>
                <template v-else-if="l.age">{{ t('students.age', { n: l.age }) }}</template>
              </div>
              <div class="r3">
                <LevelTag v-if="l.level_id" :id="l.level_id" /><span v-else class="muted" style="font-size: 12px">{{ t('crm.noLevel') }}</span>
                <span class="sp" />
                <UiIcon v-if="l.is_hot" name="zap" :size="14" class="redc" />
                <span v-if="l.waiting_min !== null" class="wait" :class="{ bad: isWaiting(l) }"><UiIcon name="clock" :size="16" />{{ isWaiting(l) ? `${waitLabel(l.waiting_min, units)} ${t('crm.noReply')}` : waitLabel(l.waiting_min, units) }}</span>
                <span v-else-if="l.stale" class="wait bad">{{ t('crm.stale') }}</span>
              </div>
            </article>
          </TransitionGroup>
          <p v-if="!visible(c.leads).length" class="col-empty">{{ t('crm.emptyCol') }}</p>
          <p v-if="c.total > c.leads.length" class="col-empty">{{ t('crm.more', { n: c.total - c.leads.length }) }}</p>
        </section>
      </div>
    </div>
  </template>

  <LeadCreateDrawer v-model:open="creating" @created="(l) => { load(); openId = l.id }" />
  <LeadDrawer :lead-id="openId" :pipelines="pipelines" @close="openId = null" @changed="onChanged" @removed="onRemoved" />
  <UiPrompt :open="lostMove !== null" :title="t('crm.lostTitle')" :text="t('crm.lostText')" :label="t('crm.lostReason')" reason required :confirm-label="t('crm.markLost')" danger :busy="busy" @update:open="(v) => !v && (lostMove = null)" @confirm="confirmLost" />
</template>
