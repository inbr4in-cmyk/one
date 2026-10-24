<script setup lang="ts">
import { computed } from 'vue'

/** Horizontal magnitude bars (leads by source, counts per item): one hue, label left, value right. */
const props = defineProps<{
  items: { key: string; label: string; value: number; icon?: string; iconCls?: string }[]
  format?: (v: number) => string
}>()
const max = computed(() => Math.max(1, ...props.items.map((i) => i.value)))
</script>

<template>
  <ul class="hbars">
    <li v-for="it in items" :key="it.key" :title="`${it.label}: ${format ? format(it.value) : it.value}`">
      <span v-if="it.icon" class="srcico" :class="it.iconCls"><svg><use :href="`#i-${it.icon}`" /></svg></span>
      <span class="hb-l">{{ it.label }}</span>
      <span class="hb-t" aria-hidden="true"><i :style="{ width: `${(it.value / max) * 100}%` }" /></span>
      <b class="num">{{ format ? format(it.value) : it.value }}</b>
    </li>
  </ul>
</template>
