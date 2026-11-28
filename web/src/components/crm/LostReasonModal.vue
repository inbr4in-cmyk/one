<script setup lang="ts">
import { ref, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiModal, UiTextarea } from '@/components/ui'
import { LOST_KINDS, type LostKind } from '@/api/crm'

/** A refusal: one reason of the list and the manager's description under it. Both are required. */
const props = defineProps<{ confirmLabel: string; busy?: boolean; kind?: LostKind | null; note?: string | null }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ confirm: [LostKind, string] }>()
const { t } = useI18n()
const formId = useId()
const kind = ref<LostKind | null>(null)
const note = ref('')
const err = ref<{ kind?: string; note?: string }>({})

watch(open, (v) => {
  if (!v) return
  kind.value = props.kind ?? null
  note.value = props.note ?? ''
  err.value = {}
})

watch([kind, note], () => (err.value = {}))

function submit() {
  err.value = { kind: kind.value ? undefined : t('crm.lostPick'), note: note.value.trim() ? undefined : t('crm.lostNoteNeed') }
  if (!kind.value || !note.value.trim()) return
  emit('confirm', kind.value, note.value.trim())
}
</script>

<template>
  <UiModal v-model:open="open" :title="t('crm.lostTitle')">
    <form :id="formId" class="stack" data-testid="lost-form" @submit.prevent="submit">
      <div class="lrk" role="radiogroup" :aria-label="t('crm.lostReason')">
        <label v-for="k in LOST_KINDS" :key="k" class="lrk-o" :class="{ on: kind === k }">
          <input v-model="kind" type="radio" name="lost-kind" :value="k" />
          <span>{{ t(`crm.lostKind.${k}`) }}</span>
        </label>
      </div>
      <p v-if="err.kind" class="form-err m0" role="alert">{{ err.kind }}</p>
      <UiTextarea v-model="note" :label="t('crm.lostNote')" :rows="3" :maxlength="255" :error="err.note" />
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="primary" type="submit" :form="formId" :loading="busy">{{ confirmLabel }}</UiButton>
    </template>
  </UiModal>
</template>

<style scoped>
.lrk { display: grid; gap: 8px }
.lrk-o { display: flex; align-items: center; gap: 10px; padding: 11px 14px; border: 1px solid var(--line); border-radius: 12px; background: var(--surface); cursor: pointer; font-weight: 600; color: var(--ink) }
.lrk-o.on { border-color: var(--navy); box-shadow: inset 0 0 0 1px var(--navy) }
.lrk-o input { accent-color: var(--navy); width: 16px; height: 16px; margin: 0 }
</style>
