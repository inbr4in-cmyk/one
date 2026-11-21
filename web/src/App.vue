<script setup lang="ts">
import IconSprite from '@/components/ui/IconSprite.vue'
import UiToastHost from '@/components/ui/UiToastHost.vue'
import UpdateGate from '@/components/layout/UpdateGate.vue'
</script>

<template>
  <IconSprite />
  <RouterView />
  <UiToastHost />
  <UpdateGate />
</template>
