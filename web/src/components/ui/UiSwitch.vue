<script setup lang="ts">
/** On/off switch (`.sw` from the design). */
defineProps<{ label: string; disabled?: boolean }>()
const model = defineModel<boolean>({ required: true })
</script>

<template>
  <button type="button" class="sw" role="switch" :aria-checked="model" :aria-label="label" :disabled="disabled" @click="model = !model" />
</template>
