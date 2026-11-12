<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import PasswordCard from '@/components/security/PasswordCard.vue'
import SessionsCard from '@/components/security/SessionsCard.vue'
import TwoFactorCard from '@/components/security/TwoFactorCard.vue'
import UiIcon from '@/components/ui/UiIcon.vue'
import UiCard from '@/components/ui/UiCard.vue'
import ThemePicker from '@/components/layout/ThemePicker.vue'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const auth = useAuthStore()
const sessionsCard = ref<InstanceType<typeof SessionsCard> | null>(null)

const totp = computed(() => auth.user?.totp_enabled ?? false)
const status = computed(() => {
  if (!auth.isStaff) return { ok: true, title: t('security.statusClientTitle'), text: t('security.statusClientText') }
  return totp.value
    ? { ok: true, title: t('security.statusOnTitle'), text: t('security.statusOnText') }
    : { ok: false, title: t('security.statusOffTitle'), text: t('security.statusOffText') }
})
</script>

<template>
  <div class="ph"><div><h1>{{ t('security.title') }}</h1><p>{{ t('security.subtitle') }}</p></div></div>
  <div class="card score">
    <span class="shield" :class="{ off: !status.ok }"><UiIcon :name="status.ok ? 'shield' : 'alert'" /></span>
    <div class="grow"><h3>{{ status.title }}</h3><div class="sub">{{ status.text }}</div></div>
  </div>
  <div class="grid sec-grid">
    <div class="grid stagger">
      <TwoFactorCard v-if="auth.isStaff" :enabled="totp" />
      <SessionsCard ref="sessionsCard" />
    </div>
    <div class="grid stagger">
      <UiCard id="appearance" :title="t('theme.title')" icon="sun">
        <ThemePicker />
      </UiCard>
      <PasswordCard v-if="auth.isStaff" @changed="sessionsCard?.reload()" />
    </div>
  </div>
</template>
