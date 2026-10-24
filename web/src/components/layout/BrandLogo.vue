<script setup lang="ts">
withDefaults(defineProps<{ size?: number; tagline?: boolean }>(), { size: 46, tagline: true })
</script>

<template>
  <span class="logo">
    <svg :width="size" :height="Math.round((size * 34) / 46)" viewBox="0 0 46 34" aria-hidden="true">
      <path fill="var(--side-indicator)" d="M1 7.5 9.5 1H15v27h3v5H2v-5h4V10.2L1 11.6z" />
      <g fill="#FFFFFF">
        <rect x="20" y="1" width="25" height="9" rx=".5" />
        <rect x="20" y="12.5" width="21" height="9" rx=".5" />
        <rect x="20" y="24" width="25" height="9" rx=".5" />
      </g>
    </svg>
    <span class="wm"><span>ONE</span><span>ENGLISH</span><small v-if="tagline">Innovation in Learning</small></span>
  </span>
</template>
