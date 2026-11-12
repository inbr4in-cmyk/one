<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiField, UiInput, UiModal, UiSegmented, UiTextarea } from '@/components/ui'
import { paymentsApi, PAYMENT_METHODS, type Payment, type PaymentMethod } from '@/api/payments'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import { isoDate, money } from '@/utils/dates'
import type { Locale } from '@/i18n'

/** Fix a payment: method, comment and (owner / branch admin) the date. Amount and lessons are not edited here. */
const props = defineProps<{ payment: Payment | null }>()
const emit = defineEmits<{ close: []; done: [] }>()
const { t, locale } = useI18n()
const auth = useAuthStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)
const form = reactive({ method: 'cash' as PaymentMethod, note: '', paid_on: '' })
const busy = ref(false)
const open = computed({ get: () => props.payment !== null, set: (v) => !v && emit('close') })
const methodOptions = computed(() => PAYMENT_METHODS.map((m) => ({ value: m, label: t(`payments.method.${m}`) })))
const canDate = computed(() => auth.can('finance.edit'))
const today = isoDate(new Date())

watch(() => props.payment, (p) => {
  if (p) Object.assign(form, { method: p.method, note: p.note ?? '', paid_on: isoDate(new Date(p.paid_at)) })
})

async function submit() {
  const p = props.payment
  if (!p || busy.value) return
  busy.value = true
  try {
    await paymentsApi.edit(p.id, {
      method: form.method,
      note: form.note.trim() || null,
      ...(canDate.value && form.paid_on ? { paid_on: form.paid_on } : {}),
    })
    toast.ok(t('payEdit.saved'))
    emit('done')
    emit('close')
  } catch {
    /* toast shown */
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiModal v-model:open="open" :title="t('payEdit.title')">
    <form v-if="payment" id="pay-edit" class="stack" @submit.prevent="submit">
      <p class="muted m0">{{ payment.student_name }} · {{ money(payment.amount, loc) }} · {{ t('students.nLessons', { n: payment.lessons }) }}</p>
      <UiField :label="t('payments.methodLabel')">
        <UiSegmented v-model="form.method" :options="methodOptions" :label="t('payments.methodLabel')" size="sm" class="wrap" />
      </UiField>
      <UiInput v-if="canDate" v-model="form.paid_on" type="date" :max="today" :label="t('payments.paidOn')" />
      <UiTextarea v-model="form.note" :label="t('payments.note')" :rows="2" :maxlength="255" />
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="navy" type="submit" form="pay-edit" :loading="busy">{{ t('common.save') }}</UiButton>
    </template>
  </UiModal>
</template>
