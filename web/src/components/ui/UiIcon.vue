<script setup lang="ts">
const props = withDefaults(defineProps<{
  name: string
  size?: 16 | 18 | 20 | 24 | 40
  /** Accessible name; without it the icon is decorative. */
  label?: string
}>(), { size: 20, label: undefined })
</script>

<template>
  <svg
    class="ico"
    :class="props.size !== 20 && `s${props.size}`"
    :role="props.label ? 'img' : undefined"
    :aria-label="props.label"
    :aria-hidden="props.label ? undefined : 'true'"
    focusable="false"
  ><use :href="`#i-${props.name}`" /></svg>
</template>
