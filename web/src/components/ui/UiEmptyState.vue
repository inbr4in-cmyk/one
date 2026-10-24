<script setup lang="ts">
import UiIcon from './UiIcon.vue'

withDefaults(defineProps<{
  icon?: string
  title: string
  text?: string
  /** Large variant: the `.stub` block from the prototype */
  large?: boolean
}>(), { icon: 'note' })
</script>

<template>
  <div :class="large ? 'stub' : 'empty'">
    <UiIcon :name="icon" />
    <h2 v-if="large">{{ title }}</h2>
    <b v-else>{{ title }}</b>
    <p v-if="text">{{ text }}</p>
    <div v-if="$slots.default" class="act"><slot /></div>
  </div>
</template>
