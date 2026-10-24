<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import UiButton from '@/components/ui/UiButton.vue'
import UiCard from '@/components/ui/UiCard.vue'
import UiChip from '@/components/ui/UiChip.vue'

defineProps<{ enabled: boolean }>()
const { t } = useI18n()
</script>

<template>
  <UiCard icon="key" :title="t('security.twoFa')">
    <template #actions>
      <UiChip :tone="enabled ? 'ok' : 'warn'">{{ enabled ? t('security.twoFaOn') : t('security.twoFaOff') }}</UiChip>
    </template>
    <div class="opt">
      <div class="grow">
        <b>{{ enabled ? t('security.twoFaOnTitle') : t('security.statusOffTitle') }}</b>
        <p>{{ enabled ? t('security.twoFaOnText') : t('security.twoFaOffText') }}</p>
      </div>
      <UiButton v-if="!enabled" size="sm" variant="primary" to="/2fa">{{ t('security.setup') }}</UiButton>
    </div>
    <div class="opt">
      <div class="grow">
        <b>{{ t('security.twoFaMethods') }}</b>
        <div class="ex">
          <UiChip :tone="enabled ? 'ok' : undefined" icon="mobile">{{ t('security.methodTotp') }}</UiChip>
        </div>
      </div>
    </div>
  </UiCard>
</template>
