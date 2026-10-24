<script setup lang="ts" generic="T extends string | number">
import UiIcon from './UiIcon.vue'

defineProps<{
  options: { value: T; label: string }[]
  label?: string
  block?: boolean
  disabled?: boolean
}>()
const model = defineModel<T>({ required: true })
</script>

<template>
  <span class="select" :class="{ block }">
    <select v-model="model" :aria-label="label" :disabled="disabled">
      <option v-for="o in options" :key="o.value" :value="o.value">{{ o.label }}</option>
    </select>
    <UiIcon name="down" :size="16" />
  </span>
</template>
