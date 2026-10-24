<script setup lang="ts">
import { computed } from 'vue'
import type { RouteLocationRaw } from 'vue-router'
import UiIcon from './UiIcon.vue'

const props = withDefaults(defineProps<{
  variant?: 'default' | 'primary' | 'navy' | 'ghost'
  size?: 'sm' | 'md' | 'lg'
  icon?: string
  /** Icon after the label */
  iconEnd?: string
  type?: 'button' | 'submit' | 'reset'
  to?: RouteLocationRaw
  href?: string
  loading?: boolean
  disabled?: boolean
  block?: boolean
  danger?: boolean
}>(), { variant: 'default', size: 'md', type: 'button' })

const cls = computed(() => [
  'btn',
  props.variant !== 'default' && props.variant,
  props.size !== 'md' && props.size,
  { full: props.block, loading: props.loading, danger: props.danger },
])
const iconSize = computed(() => (props.size === 'sm' ? 16 : 18))
</script>

<template>
  <RouterLink v-if="to" :to="to" :class="cls">
    <UiIcon v-if="icon" :name="icon" :size="iconSize" /><slot /><UiIcon v-if="iconEnd" :name="iconEnd" :size="16" />
  </RouterLink>
  <a v-else-if="href" :href="href" :class="cls">
    <UiIcon v-if="icon" :name="icon" :size="iconSize" /><slot /><UiIcon v-if="iconEnd" :name="iconEnd" :size="16" />
  </a>
  <button v-else :type="type" :class="cls" :disabled="disabled || loading" :aria-busy="loading || undefined">
    <span v-if="loading" class="spin" aria-hidden="true" />
    <UiIcon v-else-if="icon" :name="icon" :size="iconSize" />
    <span class="lbl"><slot /></span>
    <UiIcon v-if="iconEnd && !loading" :name="iconEnd" :size="16" />
  </button>
</template>
