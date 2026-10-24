<script setup lang="ts">
import { useId } from 'vue'
import UiField from './UiField.vue'

withDefaults(defineProps<{
  label?: string
  hint?: string
  error?: string | null
  placeholder?: string
  rows?: number
  maxlength?: number
  disabled?: boolean
}>(), { rows: 3, error: null })
const model = defineModel<string>({ default: '' })
const id = useId()
</script>

<template>
  <UiField :label="label" :hint="hint" :error="error" :for="id">
    <textarea
      :id="id"
      v-model="model"
      class="inp area"
      :class="{ invalid: !!error }"
      :rows="rows"
      :placeholder="placeholder"
      :maxlength="maxlength"
      :disabled="disabled"
      :aria-invalid="!!error || undefined"
    />
  </UiField>
</template>
