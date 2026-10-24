<script setup lang="ts">
import UiModal from './UiModal.vue'

defineProps<{ title?: string }>()
const open = defineModel<boolean>('open', { required: true })
</script>

<template>
  <UiModal v-model:open="open" :title="title" drawer>
    <template v-if="$slots.header" #header><slot name="header" /></template>
    <slot />
    <template v-if="$slots.footer" #footer="{ close }"><slot name="footer" :close="close" /></template>
  </UiModal>
</template>
