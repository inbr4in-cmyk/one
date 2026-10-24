<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import UiButton from '@/components/ui/UiButton.vue'
import UiCodeInput from '@/components/ui/UiCodeInput.vue'
import UiInput from '@/components/ui/UiInput.vue'
import UiPhoneInput from '@/components/ui/UiPhoneInput.vue'
import UiIcon from '@/components/ui/UiIcon.vue'
import { useAuthStore, type LoginStep } from '@/stores/auth'
import { isCompletePhone } from '@/utils/phone'

const emit = defineEmits<{ done: [step: LoginStep] }>()
const auth = useAuthStore()
const { t } = useI18n()

const phone = ref('')
const password = ref('')
const code = ref('')
const mfaToken = ref<string | null>(null)
const busy = ref(false)
const tried = ref(false)

async function submitCredentials() {
  tried.value = true
  if (!isCompletePhone(phone.value) || !password.value) return
  busy.value = true
  try {
    const res = await auth.login(phone.value, password.value)
    if (res.step === 'mfa') {
      mfaToken.value = res.mfaToken
      tried.value = false
    } else emit('done', res)
  } catch {
    /* the error toast is shown by the API client */
  } finally {
    busy.value = false
  }
}

async function submitCode() {
  tried.value = true
  if (code.value.length !== 6 || !mfaToken.value || busy.value) return
  busy.value = true
  try {
    emit('done', await auth.verifyMfa(mfaToken.value, code.value))
  } catch {
    code.value = ''
  } finally {
    busy.value = false
  }
}

function back() {
  mfaToken.value = null
  code.value = ''
  password.value = ''
  tried.value = false
}
</script>

<template>
  <Transition name="swap" mode="out-in">
    <form v-if="!mfaToken" key="creds" class="stack" novalidate @submit.prevent="submitCredentials">
      <UiPhoneInput v-model="phone" :label="t('login.phone')" autofocus :error="tried && !isCompletePhone(phone) ? t('login.phoneInvalid') : null" />
      <UiInput
        v-model="password"
        type="password"
        :label="t('login.password')"
        autocomplete="current-password"
        :error="tried && !password ? t('login.passwordRequired') : null"
      />
      <UiButton type="submit" variant="primary" size="lg" block :loading="busy">{{ t('login.submit') }}</UiButton>
      <p class="legal">{{ t('login.forgot') }}</p>
    </form>
    <form v-else key="mfa" class="stack" novalidate @submit.prevent="submitCode">
      <div class="step-h">
        <button type="button" class="back" @click="back"><UiIcon name="arrow" :size="16" />{{ t('common.back') }}</button>
        <h2>{{ t('login.mfaTitle') }}</h2>
        <p class="note">{{ t('login.mfaText') }}</p>
      </div>
      <UiCodeInput
        v-model="code"
        :label="t('login.code')"
        autofocus
        :disabled="busy"
        :error="tried && code.length !== 6 ? t('login.codeInvalid') : null"
        @complete="submitCode"
      />
      <UiButton type="submit" variant="primary" size="lg" block :loading="busy">{{ t('login.confirm') }}</UiButton>
    </form>
  </Transition>
</template>
