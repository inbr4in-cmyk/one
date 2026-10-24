<script setup lang="ts">
import { computed } from 'vue'
import { avatarColor, initials } from '@/utils/format'

const props = defineProps<{
  name: string
  /** Color class 1..8; derived from `name` when omitted. */
  color?: number
  size?: 'sm' | 'md' | 'lg'
  src?: string | null
  /** Channel badge in the corner */
  channel?: 'ig' | 'wa'
}>()

const colorCls = computed(() => `c${props.color ?? avatarColor(props.name)}`)
const channelIcon = computed(() => (props.channel === 'ig' ? 'ig' : 'wa'))
</script>

<template>
  <span class="av" :class="[colorCls, size !== 'md' && size]" :title="name">
    <img v-if="src" :src="src" alt="" />
    <template v-else>{{ initials(name) }}</template>
    <span v-if="channel" class="ch" :class="channel"><svg aria-hidden="true"><use :href="`#i-${channelIcon}`" /></svg></span>
  </span>
</template>
