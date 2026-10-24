<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiField, UiInput, UiModal, UiSegmented, UiSkeleton, UiTextarea } from '@/components/ui'
import { paymentsApi, PAYMENT_METHODS, type PaymentMethod, type Quote } from '@/api/payments'
import type { Student } from '@/api/students'
import { ApiError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import { money } from '@/utils/dates'
import type { Locale } from '@/i18n'

const props = defineProps<{ student: Student }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ paid: [] }>()
const { t, locale } = useI18n()
const auth = useAuthStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)

const PACKS = [8, 12, 24]
const form = reactive({ lessons: '12', method: 'kaspi' as PaymentMethod, discount: '', promo: '', note: '' })
const quote = ref<Quote | null>(null)
const quoteError = ref<string | null>(null)
const quoting = ref(false)
const busy = ref(false)
let seq = 0

const methodOptions = computed(() => PAYMENT_METHODS.map((m) => ({ value: m, label: t(`payments.method.${m}`) })))
const lessons = computed(() => Math.max(0, Math.floor(Number(form.lessons) || 0)))
const body = computed(() => ({
  student_id: props.student.id,
  lessons: lessons.value,
  method: form.method,
  discount: auth.can('payments.discount') ? Math.max(0, Number(form.discount) || 0) : 0,
  promo_code: form.promo.trim() || null,
  note: form.note.trim() || null,
}))

watch(open, (v) => {
  if (!v) return
  Object.assign(form, { lessons: '12', method: 'kaspi', discount: '', promo: '', note: '' })
  quote.value = null
})

let timer: ReturnType<typeof setTimeout> | undefined
watch([open, () => JSON.stringify({ ...body.value, method: '', note: '' })], () => {
  if (!open.value) return
  clearTimeout(timer)
  timer = setTimeout(fetchQuote, 250)
})

async function fetchQuote() {
  if (lessons.value < 1) {
    quote.value = null
    quoteError.value = t('payments.lessonsMin')
    return
  }
  const my = ++seq
  quoting.value = true
  try {
    const q = await paymentsApi.quote(body.value)
    if (my === seq) {
      quote.value = q
      quoteError.value = null
    }
  } catch (e) {
    if (my === seq) {
      quote.value = null
      quoteError.value = e instanceof ApiError ? e.detail : null
    }
  } finally {
    if (my === seq) quoting.value = false
  }
}

async function submit() {
  if (!quote.value) return
  busy.value = true
  try {
    await paymentsApi.create(body.value)
    toast.ok(t('payments.done', { sum: money(quote.value.to_pay, loc.value) }))
    emit('paid')
    open.value = false
  } catch {
    /* toast shown */
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiModal v-model:open="open" :title="t('payments.take')">
    <form id="pay-form" class="stack" @submit.prevent="submit">
      <p class="muted m0">{{ student.full_name }} · {{ t('payments.left', { n: student.balance.lessons_left }) }}</p>
      <UiField :label="t('payments.lessons')">
        <div class="pack-row">
          <button v-for="p in PACKS" :key="p" type="button" class="tgl" :aria-pressed="lessons === p" @click="form.lessons = String(p)">{{ p }}</button>
          <UiInput v-model="form.lessons" type="number" inputmode="numeric" :min="1" :max="200" class="pack-inp" :placeholder="t('payments.other')" />
        </div>
      </UiField>
      <UiField :label="t('payments.methodLabel')">
        <UiSegmented v-model="form.method" :options="methodOptions" :label="t('payments.methodLabel')" size="sm" class="wrap" />
      </UiField>
      <div class="form-2">
        <UiInput v-if="auth.can('payments.discount')" v-model="form.discount" type="number" inputmode="numeric" :min="0" :label="t('payments.discount')" />
        <UiInput v-model="form.promo" :label="t('payments.promo')" autocomplete="off" />
      </div>
      <UiTextarea v-model="form.note" :label="t('payments.note')" :rows="2" />

      <div class="quote" aria-live="polite">
        <template v-if="quote">
          <dl class="kv">
            <dt>{{ t('payments.q.price') }}</dt><dd class="num">{{ money(quote.lesson_price, loc) }} × {{ quote.lessons }}</dd>
            <dt>{{ t('payments.q.gross') }}</dt><dd class="num">{{ money(quote.gross, loc) }}</dd>
            <template v-if="quote.discount"><dt>{{ t('payments.q.discount') }}</dt><dd class="num okc">−{{ money(quote.discount, loc) }}</dd></template>
            <template v-if="quote.money_balance_used"><dt>{{ t('payments.q.balance') }}</dt><dd class="num okc">−{{ money(quote.money_balance_used, loc) }}</dd></template>
          </dl>
          <div class="total"><span>{{ t('payments.q.toPay') }}</span><b class="num">{{ money(quote.to_pay, loc) }}</b></div>
        </template>
        <p v-else-if="quoteError" class="form-err m0" role="alert">{{ quoteError }}</p>
        <UiSkeleton v-else :lines="3" />
      </div>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="primary" type="submit" form="pay-form" icon="wallet" :loading="busy" :disabled="!quote || quoting">
        {{ quote ? t('payments.accept', { sum: money(quote.to_pay, loc) }) : t('payments.take') }}
      </UiButton>
    </template>
  </UiModal>
</template>
