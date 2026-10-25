<script setup lang="ts">
import { computed, ref, type Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import AuthBrandPanel from '@/components/auth/AuthBrandPanel.vue'
import OtpLoginForm from '@/components/auth/OtpLoginForm.vue'
import PrefsBar from '@/components/auth/PrefsBar.vue'
import StaffLoginForm from '@/components/auth/StaffLoginForm.vue'
import UiIcon from '@/components/ui/UiIcon.vue'
import UiTabs from '@/components/ui/UiTabs.vue'
import type { LoginStep } from '@/stores/auth'
import { homePath } from '@/router'

type Mode = 'staff' | 'client'

/** Offline demo build only: role buttons instead of credentials (installed by src/demo/entry.ts). */
const DemoLogin = import.meta.env.VITE_DEMO === '1' ? ((globalThis as { __oeDemoLogin?: Component }).__oeDemoLogin ?? null) : null

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const mode = ref<Mode>(route.query.as === 'client' ? 'client' : 'staff')
const tabs = computed<{ value: Mode; label: string }[]>(() => [
  { value: 'staff', label: t('login.tabStaff') },
  { value: 'client', label: t('login.tabClient') },
])

/** Only same-app paths are accepted as a redirect target. */
function safeRedirect(): string | null {
  const r = route.query.redirect
  return typeof r === 'string' && r.startsWith('/') && !r.startsWith('//') ? r : null
}

function onDone(step: LoginStep) {
  if (step.step === 'setup') router.replace({ name: 'setup-2fa' })
  else router.replace(safeRedirect() ?? homePath())
}
</script>

<template>
  <div class="auth">
    <AuthBrandPanel />
    <main class="auth-form">
      <div class="tools"><PrefsBar /></div>
      <div class="box">
        <h1>{{ t('login.title') }}</h1>
        <p class="sub">{{ t('login.subtitle') }}</p>
        <component :is="DemoLogin" v-if="DemoLogin" @done="onDone" />
        <UiTabs v-else v-model="mode" :items="tabs" :label="t('login.title')" />
        <Transition v-if="!DemoLogin" name="swap" mode="out-in">
          <StaffLoginForm v-if="mode === 'staff'" key="staff" @done="onDone" />
          <OtpLoginForm v-else key="client" @done="onDone" />
        </Transition>
        <p class="legal"><UiIcon name="lock" :size="16" />{{ t('login.secure') }}</p>
      </div>
    </main>
  </div>
</template>
