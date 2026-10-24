<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { toDataURL } from 'qrcode'
import BrandLogo from '@/components/layout/BrandLogo.vue'
import PrefsBar from '@/components/auth/PrefsBar.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiCard from '@/components/ui/UiCard.vue'
import UiCodeInput from '@/components/ui/UiCodeInput.vue'
import UiEmptyState from '@/components/ui/UiEmptyState.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { authApi, type TotpSetup } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import { homePath } from '@/router'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const toast = useToastStore()

const setup = ref<TotpSetup | null>(null)
const qr = ref('')
const failed = ref(false)
const code = ref('')
const busy = ref(false)
const tried = ref(false)

const secretGroups = computed(() => setup.value?.secret.match(/.{1,4}/g)?.join(' ') ?? '')

async function load() {
  failed.value = false
  try {
    setup.value = await authApi.totpSetup()
    // QR stays dark-on-white in both themes so every camera reads it.
    qr.value = await toDataURL(setup.value.uri, {
      margin: 0, width: 328, errorCorrectionLevel: 'M', color: { dark: '#01225F', light: '#FFFFFF' },
    })
  } catch {
    failed.value = true
  }
}

async function copySecret() {
  if (!setup.value) return
  try {
    await navigator.clipboard.writeText(setup.value.secret)
    toast.ok(t('common.copied'))
  } catch {
    /* clipboard blocked: the key is visible and selectable */
  }
}

async function enable() {
  tried.value = true
  if (code.value.length !== 6 || busy.value) return
  busy.value = true
  try {
    await auth.enableTotp(code.value)
    toast.ok(t('setup2fa.enabled'))
    router.replace(homePath())
  } catch {
    code.value = ''
  } finally {
    busy.value = false
  }
}

async function logout() {
  await auth.logout()
  router.replace({ name: 'login' })
}

onMounted(load)
</script>

<template>
  <div class="setup">
    <header class="bar">
      <BrandLogo :size="36" :tagline="false" />
      <span class="sp" />
      <UiButton size="sm" variant="ghost" icon="logout" class="on-dark" @click="logout">{{ t('setup2fa.logoutInstead') }}</UiButton>
    </header>
    <main class="wrap">
      <div class="ph">
        <div><h1>{{ t('setup2fa.title') }}</h1><p>{{ t('setup2fa.subtitle') }}</p></div>
        <span class="sp" />
        <div class="row-actions"><PrefsBar /></div>
      </div>
      <UiCard>
        <UiEmptyState v-if="failed" large icon="alert" :title="t('errors.generic')" :text="t('setup2fa.loadError')">
          <UiButton variant="navy" @click="load">{{ t('common.retry') }}</UiButton>
        </UiEmptyState>
        <ol v-else class="steps stagger">
          <li>
            <span class="n">1</span>
            <div><b>{{ t('setup2fa.step1') }}</b><p>{{ t('setup2fa.step1Text') }}</p></div>
          </li>
          <li>
            <span class="n">2</span>
            <div>
              <b>{{ t('setup2fa.step2') }}</b><p>{{ t('setup2fa.step2Text') }}</p>
              <div class="qr-wrap">
                <div class="qr">
                  <img v-if="qr" :src="qr" :alt="t('setup2fa.qrAlt')" width="164" height="164" />
                  <UiSkeleton v-else width="164px" height="164px" />
                </div>
                <div class="secret">
                  <span class="lb">{{ t('setup2fa.secret') }}</span>
                  <span v-if="setup" class="code">{{ secretGroups }}</span>
                  <UiSkeleton v-else width="220px" height="28px" />
                  <div><UiButton size="sm" icon="file" :disabled="!setup" @click="copySecret">{{ t('common.copy') }}</UiButton></div>
                </div>
              </div>
            </div>
          </li>
          <li>
            <span class="n">3</span>
            <form class="stack" novalidate @submit.prevent="enable">
              <div><b>{{ t('setup2fa.step3') }}</b><p>{{ t('setup2fa.step3Text') }}</p></div>
              <div class="code-box">
                <UiCodeInput
                  v-model="code"
                  :disabled="busy || !setup"
                  :error="tried && code.length !== 6 ? t('login.codeInvalid') : null"
                  @complete="enable"
                />
              </div>
              <div><UiButton type="submit" variant="primary" icon="shield" :loading="busy" :disabled="!setup">{{ t('setup2fa.enable') }}</UiButton></div>
            </form>
          </li>
        </ol>
      </UiCard>
    </main>
  </div>
</template>
