<script setup lang="ts">
import { ref, useId, watch } from 'vue'
import UiField from './UiField.vue'

const props = withDefaults(defineProps<{
  label?: string
  hint?: string
  error?: string | null
  length?: number
  autofocus?: boolean
  disabled?: boolean
}>(), { length: 6, error: null })
const emit = defineEmits<{ complete: [code: string] }>()
const model = defineModel<string>({ default: '' })
const id = useId()
const el = ref<HTMLInputElement | null>(null)

function onInput(e: Event) {
  const input = e.target as HTMLInputElement
  const clean = input.value.replace(/\D/g, '').slice(0, props.length)
  input.value = clean
  model.value = clean
}

watch(model, (v) => {
  if (v.length === props.length) emit('complete', v)
})

defineExpose({ focus: () => el.value?.focus() })
</script>

<template>
  <UiField :label="label" :hint="hint" :error="error" :for="id">
    <div class="inp code" :class="{ invalid: !!error, disabled }">
      <input
        :id="id"
        ref="el"
        :value="model"
        type="text"
        inputmode="numeric"
        autocomplete="one-time-code"
        pattern="[0-9]*"
        :maxlength="length"
        placeholder="••••••"
        :autofocus="autofocus"
        :disabled="disabled"
        :aria-invalid="!!error || undefined"
        @input="onInput"
      />
    </div>
  </UiField>
</template>
