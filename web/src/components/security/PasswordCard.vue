<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import UiButton from '@/components/ui/UiButton.vue'
import UiCard from '@/components/ui/UiCard.vue'
import UiInput from '@/components/ui/UiInput.vue'
import { authApi } from '@/api/auth'
import { useToastStore } from '@/stores/toast'

const MIN = 10
const emit = defineEmits<{ changed: [] }>()
const { t } = useI18n()
const toast = useToastStore()

const oldPw = ref('')
const newPw = ref('')
const repeat = ref('')
const busy = ref(false)
const tried = ref(false)

const errors = computed(() => ({
  old: !oldPw.value ? t('login.passwordRequired') : null,
  new: newPw.value.length < MIN ? t('security.passwordShort')
    : newPw.value === oldPw.value ? t('security.passwordSame') : null,
  repeat: repeat.value !== newPw.value ? t('security.passwordMismatch') : null,
}))
const valid = computed(() => !errors.value.old && !errors.value.new && !errors.value.repeat)

async function submit() {
  tried.value = true
  if (!valid.value) return
  busy.value = true
  try {
    await authApi.changePassword(oldPw.value, newPw.value)
    toast.ok(t('security.passwordChanged'))
    oldPw.value = newPw.value = repeat.value = ''
    tried.value = false
    emit('changed')
  } catch {
    /* server detail (e.g. weak password) is shown as a toast */
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiCard icon="lock" :title="t('security.password')">
    <form class="stack" novalidate @submit.prevent="submit">
      <p class="form-note">{{ t('security.passwordText') }}</p>
      <UiInput v-model="oldPw" type="password" :label="t('security.oldPassword')" autocomplete="current-password" :error="tried ? errors.old : null" />
      <UiInput
        v-model="newPw"
        type="password"
        :label="t('security.newPassword')"
        autocomplete="new-password"
        :hint="t('security.passwordRules')"
        :error="tried ? errors.new : null"
      />
      <UiInput v-model="repeat" type="password" :label="t('security.repeatPassword')" autocomplete="new-password" :error="tried ? errors.repeat : null" />
      <div><UiButton type="submit" variant="navy" :loading="busy">{{ t('security.passwordChange') }}</UiButton></div>
    </form>
  </UiCard>
</template>
