<script setup lang="ts">
import { useSourceLabel } from '@/composables/useSourceLabel'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { UiAvatar, UiButton, UiChip, UiDrawer, UiField, UiIcon, UiInput, UiModal, UiPrompt, UiSegmented, UiSelect, UiSkeleton, UiTextarea } from '@/components/ui'
import LevelTag from '@/components/students/LevelTag.vue'
import LinkStudentModal from './LinkStudentModal.vue'
import TrialPicker from './TrialPicker.vue'
import { crmApi, type Lead, type LeadDetails, type Pipeline, type Stage } from '@/api/crm'
import type { Lesson } from '@/api/academics'
import { useAuthStore } from '@/stores/auth'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import { dayLabel, dmy, hm } from '@/utils/dates'
import { relativeTime } from '@/utils/format'
import { formatPhone } from '@/utils/phone'
import type { Locale } from '@/i18n'

const props = defineProps<{ leadId: number | null; pipelines: Pipeline[] }>()
const emit = defineEmits<{ close: []; changed: [Lead]; removed: [number] }>()
const { t, te, locale } = useI18n()
const srcLabel = useSourceLabel()
const router = useRouter()
const auth = useAuthStore()
const refs = useRefsStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)

const d = ref<LeadDetails | null>(null)
const eventKind = ref<'call' | 'note' | 'meeting'>('call')
const eventText = ref('')
const busy = ref(false)
const trialOpen = ref(false)
const lostPrompt = ref<Stage | null>(null)
const archivePrompt = ref(false)
const linkOpen = ref(false)
const phone = ref('')

const open = computed({ get: () => props.leadId !== null, set: (v) => !v && emit('close') })
const lead = computed(() => d.value?.lead ?? null)
const stages = computed(() => [...(props.pipelines.find((p) => p.id === lead.value?.pipeline_id)?.stages ?? [])].sort((a, b) => a.order - b.order))
const stage = computed(() => stages.value.find((s) => s.id === lead.value?.stage_id))
const steps = computed(() => stages.value.filter((s) => !s.is_lost))
const curIdx = computed(() => steps.value.findIndex((s) => s.id === lead.value?.stage_id))
const canEdit = computed(() => auth.can('crm.edit') && lead.value?.can_edit !== false)
const stageOptions = computed(() => stages.value.filter((s) => s.code !== 'trial_done').map((s) => ({ value: s.id, label: stageName(s) })))
const stageName = (s: Stage) => (te(`crm.stage.${s.code}`) ? t(`crm.stage.${s.code}`) : s.name)
const channel = computed(() => (lead.value?.source === 'instagram' ? 'ig' : lead.value?.source === 'whatsapp' ? 'wa' : undefined))

async function load(id: number) {
  d.value = null
  trialOpen.value = false
  assigneeOpen.value = false
  try {
    d.value = await crmApi.get(id)
  } catch {
    emit('close')
  }
}
watch(() => props.leadId, (id) => id && load(id), { immediate: true })

function updated(l: Lead) {
  if (d.value) d.value = { ...d.value, lead: l }
  emit('changed', l)
}

async function addEvent() {
  const l = lead.value
  if (!l || eventText.value.trim().length < 2) return
  busy.value = true
  try {
    await crmApi.event(l.id, { kind: eventKind.value, text: eventText.value.trim() })
    eventText.value = ''
    await load(l.id)
    if (lead.value) emit('changed', lead.value)
  } finally {
    busy.value = false
  }
}

const stageSel = ref(0)
watch(lead, (l) => (stageSel.value = l?.stage_id ?? 0))
async function changeStage(id: number) {
  const l = lead.value
  const s = stages.value.find((x) => x.id === id)
  if (!l || !s || id === l.stage_id) return
  if (s.is_lost) {
    lostPrompt.value = s
    stageSel.value = l.stage_id
    return
  }
  try {
    updated(await crmApi.stage(l.id, id))
    await load(l.id)
  } catch {
    stageSel.value = l.stage_id
  }
}
async function confirmLost(reason: string) {
  const l = lead.value
  if (!l || !lostPrompt.value) return
  busy.value = true
  try {
    updated(await crmApi.stage(l.id, lostPrompt.value.id, reason))
    lostPrompt.value = null
    await load(l.id)
  } finally {
    busy.value = false
  }
}

function openTrial() {
  trialOpen.value = !trialOpen.value
}
async function bookTrial(lesson: Lesson) {
  const l = lead.value
  if (!l) return
  busy.value = true
  try {
    updated(await crmApi.trial(l.id, lesson.id))
    toast.ok(t('crm.trialBooked', { when: `${dayLabel(lesson.starts_at, loc.value)} ${hm(lesson.starts_at, loc.value)}` }))
    trialOpen.value = false
    await load(l.id)
  } finally {
    busy.value = false
  }
}

async function bookIndividual(body: { teacher_id: number; branch_id: number; starts_at: string; minutes: number }) {
  const l = lead.value
  if (!l) return
  busy.value = true
  try {
    updated(await crmApi.trialIndividual(l.id, body))
    toast.ok(t('crm.trialBooked', { when: `${dayLabel(body.starts_at, loc.value)} ${hm(body.starts_at, loc.value)}` }))
    trialOpen.value = false
    await load(l.id)
  } finally {
    busy.value = false
  }
}

async function convert() {
  const l = lead.value
  if (!l) return
  busy.value = true
  try {
    const r = await crmApi.convert(l.id)
    toast.ok(t('crm.converted'))
    router.push({ name: 'student', params: { id: r.student_id } })
  } finally {
    busy.value = false
  }
}

const branchOptions = computed(() => [
  ...(lead.value?.branch_id ? [] : [{ value: 0, label: t('nv.noBranch') }]),
  ...refs.branches.map((b) => ({ value: b.id, label: b.name })),
])
async function setBranch(id: number) {
  const l = lead.value
  if (!l || !id || id === l.branch_id) return
  updated(await crmApi.patch(l.id, { branch_id: id }))
  await load(l.id)
}

const assigneeOpen = ref(false)
const staffOptions = computed(() => [
  ...(lead.value?.assignee_id ? [] : [{ value: 0, label: t('crm.unassigned') }]),
  ...refs.staff.filter((u) => !u.roles || u.roles.some((r) => r !== 'teacher')).map((u) => ({ value: u.id, label: u.full_name })),
])
async function openAssignee() {
  await refs.loadStaff()
  assigneeOpen.value = true
}
async function setAssignee(id: number) {
  const l = lead.value
  assigneeOpen.value = false
  if (!l || !id || id === l.assignee_id) return
  updated(await crmApi.patch(l.id, { assignee_id: id }))
  toast.ok(t('common.saved'))
  await load(l.id)
}

async function savePhone() {
  const l = lead.value
  if (!l || phone.value.trim().length < 5) return
  busy.value = true
  try {
    updated(await crmApi.patch(l.id, { phone: phone.value.trim() }))
    phone.value = ''
  } finally {
    busy.value = false
  }
}

/* ---- «Редактировать»: fix a name or a phone typed wrong ---- */
const editOpen = ref(false)
const edit = ref({ full_name: '', phone: '', age: '', parent_name: '', parent_phone: '', level_id: 0, notes: '' })
const levelOptions = computed(() => [{ value: 0, label: '—' }, ...refs.levels.map((x) => ({ value: x.id, label: x.name }))])
function openEdit() {
  const l = lead.value
  if (!l) return
  edit.value = { full_name: l.full_name, phone: l.phone ?? '', age: l.age ? String(l.age) : '', parent_name: l.parent_name ?? '',
    parent_phone: l.parent_phone ?? '', level_id: l.level_id ?? 0, notes: l.notes ?? '' }
  editOpen.value = true
}
async function saveEdit() {
  const l = lead.value
  const e = edit.value
  if (!l || !e.full_name.trim()) return
  busy.value = true
  try {
    updated(await crmApi.patch(l.id, {
      full_name: e.full_name.trim(), phone: e.phone.trim() || null, age: Number(e.age) || null, parent_name: e.parent_name.trim() || null,
      parent_phone: e.parent_phone.trim() || null, level_id: e.level_id || null, notes: e.notes.trim() || null,
    }))
    toast.ok(t('common.saved'))
    editOpen.value = false
    await load(l.id)
  } finally {
    busy.value = false
  }
}

async function linkStudent(studentId: number) {
  const l = lead.value
  if (!l) return
  busy.value = true
  try {
    await crmApi.linkStudent(l.id, studentId)
    toast.ok(t('nv.link.done'))
    linkOpen.value = false
    emit('removed', l.id)
    emit('close')
    router.push({ name: 'student', params: { id: studentId } })
  } finally {
    busy.value = false
  }
}

async function toggleHot() {
  const l = lead.value
  if (!l) return
  updated(await crmApi.patch(l.id, { is_hot: !l.is_hot }))
}

async function archive() {
  const l = lead.value
  if (!l) return
  busy.value = true
  try {
    await crmApi.archive(l.id)
    toast.ok(t('crm.archived'))
    archivePrompt.value = false
    emit('removed', l.id)
    emit('close')
  } finally {
    busy.value = false
  }
}

const EVENT_ICONS: Record<string, string> = { call: 'call', note: 'note', meeting: 'users', stage: 'arrow', sale: 'wallet', trial: 'cal', message: 'chat', created: 'zap', test: 'tests' }
const eventOptions = computed(() => (['call', 'note', 'meeting'] as const).map((k) => ({ value: k, label: t(`crm.event.${k}`) })))
</script>

<template>
  <UiDrawer v-model:open="open" :title="lead?.full_name ?? t('crm.lead')">
    <div v-if="!lead" class="stack"><UiSkeleton :lines="6" /></div>
    <div v-else class="stack lead-d">
      <div style="display: flex; gap: 12px; align-items: center">
        <UiAvatar :name="lead.full_name" size="lg" :channel="channel" />
        <div class="grow">
          <b style="font-size: 15px">{{ lead.full_name }}</b>
          <div class="muted" style="font-size: 12.5px">{{ t('crm.leadN', { n: lead.id }) }} · {{ relativeTime(lead.created_at, loc) }}</div>
        </div>
        <UiButton v-if="canEdit" size="sm" icon="edit" @click="openEdit">{{ t('nv.leadEditBtn') }}</UiButton>
        <button v-if="canEdit" type="button" class="iconbtn" :aria-pressed="lead.is_hot" :title="t('crm.hot')" :class="{ hot: lead.is_hot }" @click="toggleHot"><UiIcon name="zap" /></button>
      </div>

      <div class="lead-acts">
        <UiButton v-if="canEdit && !lead.student_id" variant="primary" icon="cal" block @click="openTrial">{{ lead.trial_lesson_id ? t('crm.rebookTrial') : t('crm.bookTrial') }}</UiButton>
        <UiButton v-if="lead.conversation_id && auth.can('inbox.view')" icon="inbox" block :to="`/inbox/${lead.conversation_id}`">{{ t('crm.openDialog') }}</UiButton>
        <UiButton v-if="lead.student_id && auth.can('students.view')" icon="user" block :to="{ name: 'student', params: { id: lead.student_id } }">{{ t('crm.openStudent') }}</UiButton>
        <UiButton v-else-if="!lead.student_id && stage?.is_won && auth.can('students.create')" icon="users" block :loading="busy" @click="convert">{{ t('crm.convert') }}</UiButton>
        <UiButton v-if="canEdit && !lead.student_id && auth.can('students.view')" icon="user" block @click="linkOpen = true">{{ t('nv.link.btn') }}</UiButton>
      </div>
      <div v-if="lead.existing_student && !lead.student_id" class="alert info">
        <UiIcon name="alert" />
        <div class="grow"><span>{{ t('nv.link.match', { name: lead.existing_student.full_name }) }}</span></div>
        <UiButton v-if="canEdit" size="sm" variant="navy" @click="linkOpen = true">{{ t('nv.link.do') }}</UiButton>
      </div>

      <Transition name="fade">
        <TrialPicker v-if="trialOpen" :branch-id="lead.branch_id" :busy="busy" @pick="bookTrial" @individual="bookIndividual" />
      </Transition>

      <h4 class="sec-h">{{ t('crm.stageLabel') }}</h4>
      <div v-if="!stage?.is_lost" class="stepper">
        <div v-for="(s, i) in steps" :key="s.id" class="step" :class="{ done: i < curIdx, cur: i === curIdx }"><i />{{ stageName(s) }}</div>
      </div>
      <UiChip v-else tone="red">{{ stageName(stage) }}<template v-if="lead.lost_reason"> · {{ lead.lost_reason }}</template></UiChip>
      <UiSelect v-if="canEdit" v-model="stageSel" :options="stageOptions" :label="t('crm.moveTo')" block @update:model-value="changeStage" />

      <h4 class="sec-h">{{ t('crm.data') }}</h4>
      <dl class="kv">
        <dt>{{ t('crm.sourceLabel') }}</dt><dd>{{ srcLabel(lead.source) }}</dd>
        <dt>{{ t('students.form.phone') }}</dt><dd>{{ lead.phone ? formatPhone(lead.phone) : '—' }}</dd>
        <template v-if="lead.age"><dt>{{ t('crm.age') }}</dt><dd>{{ lead.age }}</dd></template>
        <template v-if="lead.parent_name"><dt>{{ t('crm.parent') }}</dt><dd>{{ lead.parent_name }}<template v-if="lead.parent_phone"> · {{ formatPhone(lead.parent_phone) }}</template></dd></template>
        <dt>{{ t('students.form.level') }}</dt>
        <dd><LevelTag v-if="lead.level_id" :id="lead.level_id" full /><UiChip v-else tone="warn" small>{{ t('crm.noTest') }}</UiChip><template v-if="lead.placement_score !== null"> · {{ t('crm.score', { n: lead.placement_score }) }}</template></dd>
        <dt>{{ t('nv.leadOwner') }}</dt><dd>{{ lead.owner_name ?? t('crm.unassigned') }}</dd>
        <dt>{{ t('nv.assignee') }}</dt>
        <dd>
          <UiSelect v-if="assigneeOpen" :model-value="lead.assignee_id ?? 0" :options="staffOptions" :label="t('nv.assignee')" size="sm" @update:model-value="setAssignee" />
          <template v-else>
            {{ lead.assignee_name ?? t('crm.unassigned') }}
            <button v-if="canEdit" type="button" class="linkbtn" style="margin-left: 8px" @click="openAssignee">{{ t('nv.changeAssignee') }}</button>
          </template>
        </dd>
        <dt>{{ t('branch.label') }}</dt>
        <dd>
          <UiSelect v-if="canEdit && !lead.student_id" :model-value="lead.branch_id ?? 0" :options="branchOptions" :label="t('branch.label')" size="sm" @update:model-value="setBranch" />
          <template v-else>{{ lead.branch_id ? refs.branchName(lead.branch_id) : t('nv.noBranch') }}</template>
        </dd>
        <template v-if="lead.trial_at"><dt>{{ t('crm.trial') }}</dt><dd class="num">{{ dayLabel(lead.trial_at, loc) }} · {{ hm(lead.trial_at, loc) }}</dd></template>
        <template v-if="lead.trial_at && lead.trial_teacher"><dt>{{ t('nv.profile.teacher') }}</dt><dd>{{ lead.trial_teacher }}</dd></template>
      </dl>
      <form v-if="canEdit && !lead.phone && !lead.student_id" style="display: flex; gap: 8px; align-items: end" @submit.prevent="savePhone">
        <div class="grow"><UiInput v-model="phone" type="tel" :label="t('nv.link.phonePh')" placeholder="+7" /></div>
        <UiButton type="submit" size="sm" variant="navy" :loading="busy" :disabled="phone.trim().length < 5">{{ t('common.save') }}</UiButton>
      </form>
      <p v-if="lead.notes" class="m0 pre muted">{{ lead.notes }}</p>

      <template v-if="canEdit">
        <h4 class="sec-h">{{ t('crm.addEvent') }}</h4>
        <form class="stack" @submit.prevent="addEvent">
          <UiSegmented v-model="eventKind" :options="eventOptions" :label="t('crm.addEvent')" size="sm" block />
          <UiTextarea v-model="eventText" :placeholder="t(`crm.eventPh.${eventKind}`)" :rows="2" />
          <UiButton type="submit" size="sm" variant="navy" :loading="busy" :disabled="eventText.trim().length < 2">{{ t('common.add') }}</UiButton>
        </form>
      </template>

      <h4 class="sec-h">{{ t('crm.history') }}</h4>
      <ul class="tl">
        <li v-for="e in d?.events ?? []" :key="e.id">
          <UiIcon :name="EVENT_ICONS[e.kind] ?? 'note'" :size="16" />
          <div>{{ e.text ?? (te(`crm.event.${e.kind}`) ? t(`crm.event.${e.kind}`) : e.kind) }}<span>{{ e.actor_name ?? t('nv.byClient') }} · {{ dmy(e.at, loc) }} {{ hm(e.at, loc) }}</span></div>
        </li>
      </ul>
      <UiButton v-if="auth.can('crm.archive')" size="sm" variant="ghost" danger icon="archive" @click="archivePrompt = true">{{ t('crm.archive') }}</UiButton>
    </div>
  </UiDrawer>
  <UiPrompt :open="lostPrompt !== null" :title="t('crm.lostTitle')" :text="t('crm.lostText')" :label="t('crm.lostReason')" reason required :confirm-label="t('crm.markLost')" danger :busy="busy" @update:open="(v) => !v && (lostPrompt = null)" @confirm="confirmLost" />
  <UiModal :open="editOpen" :title="t('nv.leadEdit')" @update:open="(v) => (editOpen = v)">
    <form id="lead-edit" class="stack" @submit.prevent="saveEdit">
      <UiInput v-model="edit.full_name" :label="t('students.form.name')" :maxlength="255" />
      <div class="form-2">
        <UiInput v-model="edit.phone" type="tel" :label="t('students.form.phone')" placeholder="+7" />
        <UiInput v-model="edit.age" inputmode="numeric" :maxlength="2" :label="t('crm.age')" />
      </div>
      <div class="form-2">
        <UiInput v-model="edit.parent_name" :label="t('crm.parent')" :maxlength="255" />
        <UiInput v-model="edit.parent_phone" type="tel" :label="t('nv.parentPhone')" placeholder="+7" />
      </div>
      <UiField :label="t('students.form.level')"><UiSelect v-model="edit.level_id" :options="levelOptions" :label="t('students.form.level')" block /></UiField>
      <UiTextarea v-model="edit.notes" :label="t('nv.leadNote')" :rows="3" :maxlength="4000" />
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="primary" type="submit" form="lead-edit" :loading="busy" :disabled="!edit.full_name.trim()">{{ t('common.save') }}</UiButton>
    </template>
  </UiModal>
  <LinkStudentModal v-model:open="linkOpen" :busy="busy" :preset="lead?.existing_student ?? null" @confirm="linkStudent" />
  <UiPrompt :open="archivePrompt" :title="t('crm.archive')" :text="t('crm.archiveText')" :confirm-label="t('crm.archive')" danger :busy="busy" @update:open="(v) => (archivePrompt = v)" @confirm="archive" />
</template>
