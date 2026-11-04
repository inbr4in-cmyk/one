<script setup lang="ts">
import UiIcon from './UiIcon.vue'

defineProps<{
  tone?: 'ok' | 'warn' | 'red' | 'info'
  icon?: string
  small?: boolean
}>()
</script>

<template>
  <span class="chip" :class="[tone, { xs: small }]"><UiIcon v-if="icon" :name="icon" :size="16" /><span class="chip-t"><slot /></span></span>
</template>
