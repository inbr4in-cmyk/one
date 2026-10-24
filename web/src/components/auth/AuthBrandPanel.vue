<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import BrandLogo from '@/components/layout/BrandLogo.vue'

const { t } = useI18n()
</script>

<template>
  <aside class="brand">
    <div class="bg" aria-hidden="true">
      <div class="grid-lines" />
      <div class="glow a" />
      <div class="glow b" />
      <div class="bars"><i /><i /><i /></div>
    </div>
    <div class="mark"><BrandLogo :size="40" :tagline="false" /></div>
    <div class="hero">
      <h2 class="wordmark"><span>ONE</span><span>ENGLISH</span></h2>
      <p class="tagline">{{ t('app.tagline') }}</p>
      <p class="lead">{{ t('login.lead') }}</p>
    </div>
    <div class="bfoot"><span>{{ t('app.footer') }}</span><span>{{ t('app.since') }}</span></div>
  </aside>
</template>
