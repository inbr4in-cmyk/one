<script setup lang="ts">
withDefaults(defineProps<{
  width?: string
  height?: string
  circle?: boolean
  /** Render several text lines; the last one is shorter. */
  lines?: number
}>(), { width: '100%', height: '12px', lines: 0 })
</script>

<template>
  <span v-if="lines" class="sk-lines" aria-hidden="true">
    <span v-for="i in lines" :key="i" class="sk" :style="{ width: i === lines && lines > 1 ? '60%' : width, height }" />
  </span>
  <span v-else class="sk" :class="{ circle }" :style="{ width, height }" aria-hidden="true" />
</template>
