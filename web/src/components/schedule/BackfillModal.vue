<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiCheck, UiInput, UiModal } from '@/components/ui'
import { academicsApi } from '@/api/academics'
import { ApiError } from '@/api/http'
import { addDays, isoDate } from '@/utils/dates'

const props = defineProps<{ branchId: number | null }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ done: [] }>()
const { t } = useI18n()

const yesterday = isoDate(addDays(new Date(), -1))
const monthStart = (() => { const d = new Date(); d.setDate(1); return isoDate(d) })()
const f = reactive({ from: monthStart < yesterday ? monthStart : yesterday, to: yesterday, members: true })
const busy = ref(false)
const error = ref('')
const result = ref<{ created: number; groups: number; members: number; conflicts: string[] } | null>(null)
const valid = computed(() => !!f.from && !!f.to && f.from <= f.to && f.to <= yesterday)

async function run() {
  busy.value = true
  error.value = ''
  try {
    result.value = await academicsApi.backfill({ date_from: f.from, date_to: f.to, branch_id: props.branchId, members_from_start: f.members })
    if (result.value.created) emit('done')
  } catch (e) {
    error.value = e instanceof ApiError ? e.detail || t('errors.generic') : t('errors.generic')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiModal v-model:open="open" :title="t('schedule.backfill.title')">
    <p class="muted">{{ t('schedule.backfill.text') }}</p>
    <div class="row2">
      <UiInput v-model="f.from" type="date" :max="f.to" :label="t('schedule.backfill.from')" />
      <UiInput v-model="f.to" type="date" :min="f.from" :max="yesterday" :label="t('schedule.backfill.to')" />
    </div>
    <UiCheck v-model="f.members" :label="t('schedule.backfill.members')" />
    <p v-if="error" class="err" role="alert">{{ error }}</p>
    <div v-if="result" class="res" role="status">
      <b>{{ result.created ? t('schedule.backfill.done', { n: result.created, g: result.groups }) : t('schedule.backfill.none') }}</b>
      <span v-if="result.members">{{ t('schedule.backfill.membersMoved', { n: result.members }) }}</span>
      <details v-if="result.conflicts.length">
        <summary>{{ t('schedule.backfill.conflicts', { n: result.conflicts.length }) }}</summary>
        <ul><li v-for="c in result.conflicts" :key="c">{{ c }}</li></ul>
      </details>
      <span class="muted">{{ t('schedule.backfill.hint') }}</span>
    </div>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.close') }}</UiButton>
      <UiButton variant="primary" :loading="busy" :disabled="!valid" @click="run">{{ t('schedule.backfill.run') }}</UiButton>
    </template>
  </UiModal>
</template>

<style scoped>
.muted { color: var(--muted); font-size: 13px; margin: 0 0 12px; }
.row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px; }
.err { color: var(--red-600); margin: 12px 0 0; }
.res { display: grid; gap: 6px; margin-top: 14px; padding: 12px; border-radius: var(--r-sm); background: var(--navy-50); }
.res ul { margin: 6px 0 0; padding-left: 18px; max-height: 160px; overflow: auto; font-size: 13px; }
@media (max-width: 520px) { .row2 { grid-template-columns: 1fr; } }
</style>
