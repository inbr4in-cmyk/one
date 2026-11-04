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
/** Server limits (GET /payments/{id}/refundable): lessons still left from this payment and the money for them. */
const limits = ref<{ lessons_max: number; amount_max: number; amount_left: number } | null>(null)
const max = computed(() => limits.value?.amount_left ?? (props.payment ? props.payment.amount - props.payment.refunded : 0))
const lessonsMax = computed(() => limits.value?.lessons_max ?? props.payment?.lessons ?? 0)

watch(() => props.payment, async (p) => {
  limits.value = null
  if (!p) return
  Object.assign(form, { lessons: '0', amount: '', reason: '' })
  error.value = null
  const l = await paymentsApi.refundable(p.id).catch(() => null)
  if (props.payment?.id !== p.id) return
  limits.value = l
  if (l) Object.assign(form, { lessons: String(l.lessons_max), amount: String(l.amount_max) })
  else Object.assign(form, { amount: String(p.amount - p.refunded) })
})

async function submit() {
  const p = props.payment
  if (!p) return
  const amount = Math.floor(Number(form.amount) || 0)
  const lessons = Math.floor(Number(form.lessons) || 0)
  error.value = null
  if (amount < 0 || amount > max.value) error.value = t('payments.refundBadSum', { max: money(max.value, loc.value) })
  else if (lessons < 0 || lessons > lessonsMax.value) error.value = t('payments.refundLessonsBad', { n: lessonsMax.value })
  else if (amount === 0 && lessons === 0) error.value = t('payments.refundNothing')
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
        <UiInput v-model="form.amount" type="number" :min="0" :max="max" :label="t('payments.refundSum')" :hint="t('payments.refundMax', { max: money(limits && Number(form.lessons) >= limits.lessons_max ? limits.amount_max : max, loc) })" />
        <UiInput v-model="form.lessons" type="number" :min="0" :max="lessonsMax" :label="t('payments.refundLessons')" :hint="t('payments.refundLessonsMax', { n: lessonsMax })" />
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
