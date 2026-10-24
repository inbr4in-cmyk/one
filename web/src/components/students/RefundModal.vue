<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiIcon, UiInput, UiModal, UiTextarea } from '@/components/ui'
import { paymentsApi, type Payment } from '@/api/payments'
import { ApiError } from '@/api/http'
import { useToastStore } from '@/stores/toast'
import { dmy, money } from '@/utils/dates'
import type { Locale } from '@/i18n'

const props = defineProps<{ payment: Payment | null }>()
const emit = defineEmits<{ close: []; done: [] }>()
const { t, locale } = useI18n()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)
const form = reactive({ lessons: '0', amount: '', reason: '' })
const error = ref<string | null>(null)
const busy = ref(false)

const open = computed({ get: () => props.payment !== null, set: (v) => !v && emit('close') })
const max = computed(() => (props.payment ? props.payment.amount - props.payment.refunded : 0))

watch(() => props.payment, (p) => {
  if (!p) return
  const rest = p.amount - p.refunded
  Object.assign(form, { lessons: String(p.lesson_price ? Math.min(p.lessons, Math.floor(rest / p.lesson_price)) : 0), amount: String(rest), reason: '' })
  error.value = null
})

async function submit() {
  const p = props.payment
  if (!p) return
  const amount = Math.floor(Number(form.amount) || 0)
  const lessons = Math.floor(Number(form.lessons) || 0)
  error.value = null
  if (amount <= 0 || amount > max.value) error.value = t('payments.refundBadSum', { max: money(max.value, loc.value) })
  else if (form.reason.trim().length < 3) error.value = t('common.reasonRequired')
  if (error.value) return
  busy.value = true
  try {
    const r = await paymentsApi.refund(p.id, { lessons, amount, reason: form.reason.trim() })
    toast.ok(r.bonuses_reversed ? t('payments.refundDoneBonus', { n: r.bonuses_reversed }) : t('payments.refundDone'))
    emit('done')
    emit('close')
  } catch (e) {
    if (e instanceof ApiError) error.value = e.detail
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiModal v-model:open="open" :title="t('payments.refundTitle')">
    <form v-if="payment" id="rf-form" class="stack" novalidate @submit.prevent="submit">
      <p class="muted m0">
        {{ payment.student_name ?? '' }} · {{ dmy(payment.paid_at, loc) }} · {{ money(payment.amount, loc) }} · {{ t('students.nLessons', { n: payment.lessons }) }}
      </p>
      <div class="form-2">
        <UiInput v-model="form.amount" type="number" :min="1" :max="max" :label="t('payments.refundSum')" :hint="t('payments.refundMax', { max: money(max, loc) })" />
        <UiInput v-model="form.lessons" type="number" :min="0" :label="t('payments.refundLessons')" />
      </div>
      <UiTextarea v-model="form.reason" :label="t('common.reason')" :rows="2" />
      <div class="alert"><UiIcon name="alert" /><div class="grow"><span>{{ t('payments.refundNote') }}</span></div></div>
      <p v-if="error" class="form-err m0" role="alert">{{ error }}</p>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="primary" type="submit" form="rf-form" :loading="busy">{{ t('payments.refund') }}</UiButton>
    </template>
  </UiModal>
</template>
