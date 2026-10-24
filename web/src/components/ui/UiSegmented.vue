<script setup lang="ts" generic="T extends string | number">
import UiIcon from './UiIcon.vue'

defineProps<{
  options: { value: T; label: string; icon?: string; iconOnly?: boolean }[]
  label?: string
  size?: 'sm' | 'md'
  block?: boolean
}>()
const model = defineModel<T>({ required: true })
</script>

<template>
  <div class="seg" :class="{ sm: size === 'sm', full: block }" role="group" :aria-label="label">
    <button
      v-for="o in options"
      :key="o.value"
      type="button"
      :aria-pressed="model === o.value"
      :title="o.iconOnly ? o.label : undefined"
      @click="model = o.value"
    >
      <UiIcon v-if="o.icon" :name="o.icon" :size="16" />
      <span :class="{ sr: o.iconOnly }">{{ o.label }}</span>
    </button>
  </div>
</template>
