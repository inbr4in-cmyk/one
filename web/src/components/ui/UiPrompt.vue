<script setup lang="ts">
import { ref, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import UiButton from './UiButton.vue'
import UiModal from './UiModal.vue'
import UiTextarea from './UiTextarea.vue'

/** Confirm dialog with an optional (or required) reason. Emits `confirm` with the trimmed text. */
const props = defineProps<{
  title: string
  text?: string
  label?: string
  confirmLabel: string
  required?: boolean
  danger?: boolean
  busy?: boolean
  error?: string | null
  /** Show the reason field at all */
  reason?: boolean
}>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ confirm: [string] }>()
const { t } = useI18n()
const formId = useId()
const value = ref('')
const err = ref<string | null>(null)

watch(open, (v) => {
  if (v) {
    value.value = ''
    err.value = null
  }
})

function submit() {
  if (props.reason && props.required && !value.value.trim()) {
    err.value = t('common.reasonRequired')
    return
  }
  emit('confirm', value.value.trim())
}
</script>

<template>
  <UiModal v-model:open="open" :title="title">
    <form :id="formId" class="stack" @submit.prevent="submit">
      <p v-if="text" class="m0">{{ text }}</p>
      <slot />
      <UiTextarea v-if="reason" v-model="value" :label="label ?? t('common.reason')" :rows="2" :error="err ?? error" />
      <p v-else-if="error" class="form-err m0" role="alert">{{ error }}</p>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton :variant="danger ? 'primary' : 'navy'" type="submit" :form="formId" :loading="busy">{{ confirmLabel }}</UiButton>
    </template>
  </UiModal>
</template>
