<script setup lang="ts">
import UiIcon from './UiIcon.vue'

defineProps<{
  title?: string
  icon?: string
  /** Body without padding (tables, lists that bleed to the edge). */
  flush?: boolean
}>()
</script>

<template>
  <section class="card">
    <header v-if="title || $slots.header || $slots.actions" class="card-h">
      <UiIcon v-if="icon" :name="icon" />
      <slot name="header"><h3>{{ title }}</h3></slot>
      <span class="sp" />
      <slot name="actions" />
    </header>
    <slot v-if="flush" />
    <div v-else class="card-b"><slot /></div>
  </section>
</template>
