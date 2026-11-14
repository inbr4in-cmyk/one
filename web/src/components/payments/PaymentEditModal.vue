<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiField, UiInput, UiModal, UiSegmented, UiSelect, UiTextarea } from '@/components/ui'
import { ApiError } from '@/api/http'
import { paymentsApi, PAYMENT_METHODS, type Payment, type PaymentMethod } from '@/api/payments'
import { useAuthStore } from '@/stores/auth'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import { isoDate, money, schoolNow, toSchool } from '@/utils/dates'
import type { Locale } from '@/i18n'

/** Fix a payment: method, comment and, for the owner / branch admin, the date, lessons, level and amount. */
const props = defineProps<{ payment: Payment | null }>()
const emit = defineEmits<{ close: []; done: [] }>()
const { t, locale } = useI18n()
const auth = useAuthStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)
const refs = useRefsStore()
const form = reactive({ method: 'cash' as PaymentMethod, note: '', paid_on: '', lessons: '', level_id: 0, amount: '' })
const error = ref<string | null>(null)
const busy = ref(false)
const open = computed({ get: () => props.payment !== null, set: (v) => !v && emit('close') })
const methodOptions = computed(() => PAYMENT_METHODS.map((m) => ({ value: m, label: t(`payments.method.${m}`) })))
const canDate = computed(() => auth.can('finance.edit'))
const today = isoDate(schoolNow())
/** Lessons, level and amount: only for a course payment without refunds. */
const canMoney = computed(() => canDate.value && props.payment?.category === 'course' && !props.payment.refunded)
const levelOptions = computed(() => refs.levels.map((l) => ({ value: l.id, label: l.name })))

watch(() => props.payment, (p) => {
  error.value = null
  if (p) Object.assign(form, { method: p.method, note: p.note ?? '', paid_on: isoDate(toSchool(p.paid_at)), lessons: String(p.lessons), level_id: p.level_id ?? 0, amount: String(p.amount) })
})

async function submit() {
  const p = props.payment
  if (!p || busy.value) return
  error.value = null
  busy.value = true
  try {
    await paymentsApi.edit(p.id, {
      method: form.method,
      note: form.note.trim() || null,
      ...(canDate.value && form.paid_on ? { paid_on: form.paid_on } : {}),
      ...(canMoney.value ? {
        ...(form.lessons !== '' && Number(form.lessons) !== p.lessons ? { lessons: Math.max(0, Math.round(Number(form.lessons))) } : {}),
        ...(form.level_id && form.level_id !== p.level_id ? { level_id: form.level_id } : {}),
        ...(form.amount !== '' && Number(form.amount) !== p.amount ? { amount: Math.max(0, Math.round(Number(form.amount))) } : {}),
      } : {}),
    })
    toast.ok(t('payEdit.saved'))
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
  <UiModal v-model:open="open" :title="t('payEdit.title')">
    <form v-if="payment" id="pay-edit" class="stack" @submit.prevent="submit">
      <p class="muted m0">{{ payment.student_name }} · {{ money(payment.amount, loc) }} · {{ t('students.nLessons', { n: payment.lessons }) }}</p>
      <UiField :label="t('payments.methodLabel')">
        <UiSegmented v-model="form.method" :options="methodOptions" :label="t('payments.methodLabel')" size="sm" class="wrap" />
      </UiField>
      <UiInput v-if="canDate" v-model="form.paid_on" type="date" :max="today" :label="t('payments.paidOn')" />
      <template v-if="canMoney">
        <div class="form-2">
          <UiInput v-model="form.lessons" type="number" :min="0" :max="500" :label="t('nv.payLessons')" />
          <UiInput v-model="form.amount" type="number" :min="0" :label="t('nv.payAmount')" />
        </div>
        <UiField :label="t('students.form.level')"><UiSelect v-model="form.level_id" :options="levelOptions" :label="t('students.form.level')" block /></UiField>
      </template>
      <UiTextarea v-model="form.note" :label="t('payments.note')" :rows="2" :maxlength="255" />
      <p v-if="error" class="form-err m0" role="alert">{{ error }}</p>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="navy" type="submit" form="pay-edit" :loading="busy">{{ t('common.save') }}</UiButton>
    </template>
  </UiModal>
</template>
