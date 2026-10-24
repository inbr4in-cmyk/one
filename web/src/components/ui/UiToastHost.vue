<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useToastStore } from '@/stores/toast'

const toasts = useToastStore()
const { t } = useI18n()
const iconOf = { info: 'bell', ok: 'ok', error: 'alert' } as const
</script>

<template>
  <div class="toasts" role="region" aria-live="polite" :aria-label="t('top.notifications')">
    <TransitionGroup name="toast">
      <div v-for="item in toasts.items" :key="item.id" class="toast" :class="item.tone" :role="item.tone === 'error' ? 'alert' : 'status'">
        <span class="srcico"><svg aria-hidden="true"><use :href="`#i-${iconOf[item.tone]}`" /></svg></span>
        <span>{{ item.text }}</span>
        <button type="button" class="x" :aria-label="t('common.close')" @click="toasts.dismiss(item.id)">
          <svg class="ico s16" aria-hidden="true"><use href="#i-x" /></svg>
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>
