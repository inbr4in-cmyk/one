<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import UiButton from '@/components/ui/UiButton.vue'
import UiCodeInput from '@/components/ui/UiCodeInput.vue'
import UiPhoneInput from '@/components/ui/UiPhoneInput.vue'
import UiIcon from '@/components/ui/UiIcon.vue'
import { authApi } from '@/api/auth'
import { useAuthStore, type LoginStep } from '@/stores/auth'
import { formatNational, isCompletePhone, nationalDigits } from '@/utils/phone'

const RESEND_AFTER = 60

const emit = defineEmits<{ done: [step: LoginStep] }>()
const auth = useAuthStore()
const { t } = useI18n()

const phone = ref('')
const code = ref('')
const sent = ref(false)
const busy = ref(false)
const tried = ref(false)
const cooldown = ref(0)
let timer: ReturnType<typeof setInterval> | undefined

function startCooldown() {
  cooldown.value = RESEND_AFTER
  clearInterval(timer)
  timer = setInterval(() => {
    cooldown.value -= 1
    if (cooldown.value <= 0) clearInterval(timer)
  }, 1000)
}
onBeforeUnmount(() => clearInterval(timer))

async function requestCode() {
  tried.value = true
  if (!isCompletePhone(phone.value) || busy.value) return
  busy.value = true
  try {
    await authApi.otpRequest(phone.value)
    sent.value = true
    tried.value = false
    startCooldown()
  } catch {
    /* toast already shown */
  } finally {
    busy.value = false
  }
}

async function verify() {
  tried.value = true
  if (code.value.length !== 6 || busy.value) return
  busy.value = true
  try {
    emit('done', await auth.verifyOtp(phone.value, code.value))
  } catch {
    code.value = ''
  } finally {
    busy.value = false
  }
}

function changePhone() {
  sent.value = false
  code.value = ''
  tried.value = false
}
</script>

<template>
  <Transition name="swap" mode="out-in">
    <form v-if="!sent" key="phone" class="stack" novalidate @submit.prevent="requestCode">
      <p class="note">{{ t('login.otpText') }}</p>
      <UiPhoneInput v-model="phone" :label="t('login.phone')" autofocus :error="tried && !isCompletePhone(phone) ? t('login.phoneInvalid') : null" />
      <UiButton type="submit" variant="primary" size="lg" block icon="wa" :loading="busy">{{ t('login.otpSend') }}</UiButton>
    </form>
    <form v-else key="code" class="stack" novalidate @submit.prevent="verify">
      <div class="step-h">
        <button type="button" class="back" @click="changePhone"><UiIcon name="arrow" :size="16" />{{ t('login.otpChangePhone') }}</button>
        <h2>{{ t('login.otpSentTitle') }}</h2>
        <p class="note">{{ t('login.otpSentText', { phone: formatNational(nationalDigits(phone)) }) }}</p>
      </div>
      <UiCodeInput
        v-model="code"
        :label="t('login.code')"
        autofocus
        :disabled="busy"
        :error="tried && code.length !== 6 ? t('login.codeInvalid') : null"
        @complete="verify"
      />
      <UiButton type="submit" variant="primary" size="lg" block :loading="busy">{{ t('login.submit') }}</UiButton>
      <div class="resend">
        <span>{{ cooldown > 0 ? t('login.otpResendIn', { s: cooldown }) : '' }}</span>
        <button type="button" class="linkbtn" :disabled="cooldown > 0 || busy" @click="requestCode">{{ t('login.otpResend') }}</button>
      </div>
    </form>
  </Transition>
</template>
