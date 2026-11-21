<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useToastStore, type Toast } from '@/stores/toast'

const toasts = useToastStore()
const { t } = useI18n()
const router = useRouter()
function go(item: Toast) {
  if (!item.link) return
  toasts.dismiss(item.id)
  void router.push(item.link)
}
const iconOf = { info: 'bell', ok: 'ok', error: 'alert' } as const
</script>

<template>
  <div class="toasts" role="region" aria-live="polite" :aria-label="t('top.notifications')">
    <TransitionGroup name="toast">
      <div v-for="item in toasts.items" :key="item.id" class="toast" :class="[item.tone, { link: item.link }]" @click="go(item)" :role="item.tone === 'error' ? 'alert' : 'status'">
        <span class="srcico"><svg aria-hidden="true"><use :href="`#i-${iconOf[item.tone]}`" /></svg></span>
        <span>{{ item.text }}</span>
        <button type="button" class="x" :aria-label="t('common.close')" @click.stop="toasts.dismiss(item.id)">
          <svg class="ico s16" aria-hidden="true"><use href="#i-x" /></svg>
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>
