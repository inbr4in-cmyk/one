<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiIcon } from '@/components/ui'
import TaskForm, { type TaskDraft } from './TaskForm.vue'
import TaskDoneModal from './TaskDoneModal.vue'
import { leadTasksApi, type LeadTask } from '@/api/crm'
import { nowMs } from '@/utils/clock'
import { dayLabel, hm, schoolIso, todayIso } from '@/utils/dates'
import type { Locale } from '@/i18n'

/** The lead's tasks inside its card: every open lead has a next task, the manager sets it for himself. */
const props = defineProps<{ leadId: number; canEdit: boolean; closed: boolean }>()
const emit = defineEmits<{ changed: [] }>()
const { t, locale } = useI18n()
const loc = computed(() => locale.value as Locale)
const items = ref<LeadTask[] | null>(null)
const draft = ref<TaskDraft>(blank())
const adding = ref(false)
const busy = ref(false)
const closing = ref<LeadTask | null>(null)

function blank(): TaskDraft {
  return { title: '', date: todayIso(), time: '10:00', daily: false }
}
async function load() {
  items.value = await leadTasksApi.ofLead(props.leadId).catch(() => [])
  adding.value = !items.value.length && !props.closed && props.canEdit
}
watch(() => props.leadId, () => {
  items.value = null
  draft.value = blank()
  load()
}, { immediate: true })

const overdue = (x: LeadTask) => !!x.due_at && new Date(x.due_at).getTime() < nowMs()
async function add() {
  const f = draft.value
  if (!f.title.trim() || !f.date) return
  busy.value = true
  try {
    await leadTasksApi.add(props.leadId, { title: f.title.trim(), due_at: schoolIso(f.date, f.time || '10:00'), daily: f.daily })
    draft.value = blank()
    await load()
    emit('changed')
  } catch {
    /* toast shown by the client */
  } finally {
    busy.value = false
  }
}
async function onDone() {
  await load()
  emit('changed')
}
</script>

<template>
  <div class="lt">
    <div class="lt-h">
      <h4 class="sec-h m0">{{ t('nv.lt.title') }}</h4>
      <span v-if="items && !items.length && !closed" class="chip red xs"><span class="chip-t">{{ t('nv.lt.none') }}</span></span>
      <span class="sp" />
      <button v-if="canEdit && !closed && !adding" type="button" class="linkbtn" @click="adding = true">{{ t('nv.lt.add') }}</button>
    </div>
    <ul v-if="items?.length" class="lt-list">
      <li v-for="x in items" :key="x.id" :class="{ bad: overdue(x) }">
        <UiIcon :name="x.daily ? 'history' : 'clock'" :size="16" />
        <div class="grow">
          <b>{{ x.title }}</b>
          <span>{{ x.due_at ? `${dayLabel(x.due_at, loc, { day: 'numeric', month: 'short' })}, ${hm(x.due_at, loc)}` : '' }}<template v-if="x.daily"> · {{ t('nv.lt.dailyShort') }}</template><template v-if="x.assignee_name"> · {{ x.assignee_name }}</template></span>
        </div>
        <UiButton v-if="canEdit" size="sm" variant="navy" icon="ok" @click="closing = x">{{ t('nv.lt.done') }}</UiButton>
      </li>
    </ul>
    <form v-if="adding && canEdit && !closed" class="stack lt-form" @submit.prevent="add">
      <TaskForm v-model="draft" :min="todayIso()" />
      <UiButton type="submit" size="sm" variant="primary" :loading="busy" :disabled="!draft.title.trim() || !draft.date">{{ t('nv.lt.set') }}</UiButton>
    </form>
    <TaskDoneModal :task="closing" @close="closing = null" @done="onDone" />
  </div>
</template>

<style scoped>
.lt { display: grid; gap: 10px }
.lt-h { display: flex; align-items: center; gap: 8px }
.lt-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px }
.lt-list li { display: flex; align-items: center; gap: 10px; padding: 8px 10px; border: 1px solid var(--line); border-radius: 10px; background: var(--surface) }
.lt-list li.bad { border-color: var(--red); box-shadow: inset 3px 0 0 var(--red) }
.lt-list li.bad span { color: var(--red-ink) }
.lt-list b { display: block; font-size: 13.5px }
.lt-list span { font-size: 12.5px; color: var(--muted) }
.lt-form { padding: 10px; border: 1px dashed var(--line); border-radius: 10px }
</style>
