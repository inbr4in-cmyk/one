<script setup lang="ts">
// Inline SVG sprite: 24×24, stroke 1.75, round caps, currentColor. Ported from docs/design.
import sprite from '@/assets/sprite.svg?raw'
</script>

<template>
  <div class="sr" aria-hidden="true" v-html="sprite" />
</template>
