<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import UiButton from './UiButton.vue'

const props = defineProps<{ total: number; limit: number }>()
const offset = defineModel<number>({ required: true })
const { t } = useI18n()

const from = computed(() => (props.total ? offset.value + 1 : 0))
const to = computed(() => Math.min(props.total, offset.value + props.limit))
</script>

<template>
  <div v-if="total > limit" class="pager">
    <span class="muted num">{{ t('common.range', { from, to, total }) }}</span>
    <span class="sp" />
    <UiButton size="sm" icon="arrow" class="flip" :disabled="offset === 0" :aria-label="t('common.prev')" @click="offset = Math.max(0, offset - limit)" />
    <UiButton size="sm" icon="arrow" :disabled="to >= total" :aria-label="t('common.next')" @click="offset = offset + limit" />
  </div>
</template>
