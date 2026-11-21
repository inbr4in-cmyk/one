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
    <div class="auth-mark" aria-hidden="true" />
    <div class="hero">
      <h2 class="hero-logo"><BrandLogo :size="84" /></h2>
      <p class="auth-lead">{{ t('login.lead') }}</p>
    </div>
    <div class="bfoot"><span>{{ t('app.footer') }}</span><span>{{ t('app.since') }}</span></div>
  </aside>
</template>
