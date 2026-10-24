<script setup lang="ts">
import { computed } from 'vue'
import { useRefsStore } from '@/stores/refs'
import { tone } from '@/utils/levels'

const props = defineProps<{ id: number | null | undefined; full?: boolean }>()
const refs = useRefsStore()
const lv = computed(() => refs.level(props.id))
</script>

<template>
  <span v-if="lv" class="lv" :style="{ '--c': tone(lv.color) }" :title="lv.name">{{ full ? lv.name : lv.code }}</span>
  <span v-else class="muted">—</span>
</template>
