<script setup lang="ts">
defineProps<{
  label?: string
  hint?: string
  error?: string | null
  /** id of the control, so the label points at it */
  for?: string
}>()
</script>

<template>
  <div class="field">
    <label v-if="label" :for="$props.for">{{ label }}</label>
    <slot />
    <span v-if="error" class="err" role="alert">{{ error }}</span>
    <span v-else-if="hint" class="hint">{{ hint }}</span>
  </div>
</template>
