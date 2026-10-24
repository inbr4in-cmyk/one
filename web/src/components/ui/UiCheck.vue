<script setup lang="ts">
defineProps<{ label: string; hint?: string; disabled?: boolean }>()
const model = defineModel<boolean>({ required: true })
</script>

<template>
  <label class="check" :class="{ disabled }">
    <input v-model="model" type="checkbox" :disabled="disabled" />
    <span class="box" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg></span>
    <span class="txt">{{ label }}<small v-if="hint">{{ hint }}</small></span>
  </label>
</template>
