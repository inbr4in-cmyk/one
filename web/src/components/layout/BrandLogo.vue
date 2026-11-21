<script setup lang="ts">
import logo from '@/assets/brand/logo.svg'
import logoTagline from '@/assets/brand/logo-tagline.svg'

/** The school's original logo (owner's vector file, 21.11.2026), on a white plate so its colours stay true on any background. */
withDefaults(defineProps<{ size?: number; tagline?: boolean }>(), { size: 46, tagline: true })
</script>

<template>
  <span class="logo">
    <img :src="tagline ? logoTagline : logo" :height="tagline ? Math.round((size * 4) / 3) : size" :width="size * 4" alt="One English" />
  </span>
</template>
