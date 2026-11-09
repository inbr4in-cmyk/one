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
const todayIso = () => { const d = new Date(); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10) }
const form = reactive({ by: 'lessons' as 'lessons' | 'amount', lessons: '12', amount: '', method: 'kaspi' as PaymentMethod, discount: '', promo: '', note: '', paid_on: todayIso() })
const byOptions = computed(() => [{ value: 'lessons', label: t('payments.byLessons') }, { value: 'amount', label: t('payments.byAmount') }])
const amount = computed(() => Math.max(0, Math.floor(Number(form.amount) || 0)))
/** Owners and branch admins may enter an earlier payment (backfilling past months). */
const canBackdate = computed(() => auth.can('finance.edit'))
const backdated = computed(() => canBackdate.value && !!form.paid_on && form.paid_on !== todayIso())
const quote = ref<Quote | null>(null)
const quoteError = ref<string | null>(null)
const quoting = ref(false)
const busy = ref(false)
let seq = 0

const methodOptions = computed(() => PAYMENT_METHODS.map((m) => ({ value: m, label: t(`payments.method.${m}`) })))
const lessons = computed(() => Math.max(0, Math.floor(Number(form.lessons) || 0)))
const byAmount = computed(() => form.by === 'amount')
const body = computed(() => ({
  student_id: props.student.id,
  lessons: byAmount.value ? 0 : lessons.value,
  amount: byAmount.value ? amount.value : null,
  method: form.method,
  discount: !byAmount.value && auth.can('payments.discount') ? Math.max(0, Number(form.discount) || 0) : 0,
  promo_code: form.promo.trim() || null,
  note: form.note.trim() || null,
  paid_on: backdated.value ? form.paid_on : null,
}))

watch(open, (v) => {
  if (!v) return
  Object.assign(form, { by: 'lessons', lessons: '12', amount: '', method: 'kaspi', discount: '', promo: '', note: '', paid_on: todayIso() })
  quote.value = null
})

let timer: ReturnType<typeof setTimeout> | undefined
watch([open, () => JSON.stringify({ ...body.value, method: '', note: '', paid_on: '' })], () => {
  if (!open.value) return
  clearTimeout(timer)
  timer = setTimeout(fetchQuote, 250)
})

async function fetchQuote() {
  if (byAmount.value ? amount.value < 1 : lessons.value < 1) {
    quote.value = null
    quoteError.value = byAmount.value ? t('payments.amountMin') : t('payments.lessonsMin')
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

/** One key per opened form: a double tap or a retry after a lost response can't charge twice. */
const newKey = () => (globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`)
let idemKey = newKey()
watch(open, (v) => {
  if (v) idemKey = newKey()
})

async function submit() {
  if (!quote.value || busy.value) return
  busy.value = true
  try {
    await paymentsApi.create(body.value, idemKey)
    idemKey = newKey()
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
      <UiSegmented v-model="form.by" :options="byOptions" :label="t('payments.byLabel')" size="sm" />
      <UiInput v-if="byAmount" v-model="form.amount" type="number" inputmode="numeric" :min="1" :label="t('payments.amount')"
        :hint="t('payments.amountHint')" autofocus />
      <UiField v-else :label="t('payments.lessons')">
        <div class="pack-row">
          <button v-for="p in PACKS" :key="p" type="button" class="tgl" :aria-pressed="lessons === p" @click="form.lessons = String(p)">{{ p }}</button>
          <UiInput v-model="form.lessons" type="number" inputmode="numeric" :min="1" :max="200" class="pack-inp" :placeholder="t('payments.other')" />
        </div>
      </UiField>
      <UiField :label="t('payments.methodLabel')">
        <UiSegmented v-model="form.method" :options="methodOptions" :label="t('payments.methodLabel')" size="sm" class="wrap" />
      </UiField>
      <div class="form-2">
        <UiInput v-if="auth.can('payments.discount') && !byAmount" v-model="form.discount" type="number" inputmode="numeric" :min="0" :label="t('payments.discount')" />
        <UiInput v-model="form.promo" :label="t('payments.promo')" autocomplete="off" />
      </div>
      <UiInput v-if="canBackdate" v-model="form.paid_on" type="date" :max="todayIso()" :label="t('payments.paidOn')"
        :hint="backdated ? t('payments.paidOnHint') : undefined" />
      <UiTextarea v-model="form.note" :label="t('payments.note')" :rows="2" />

      <div class="quote" aria-live="polite">
        <template v-if="quote">
          <dl class="kv">
            <dt>{{ t('payments.q.price') }}</dt><dd class="num">{{ money(quote.lesson_price, loc) }} × {{ quote.lessons }}</dd>
            <dt>{{ t('payments.q.gross') }}</dt><dd class="num">{{ money(quote.gross, loc) }}</dd>
            <template v-if="quote.discount"><dt>{{ t('payments.q.discount') }}</dt><dd class="num okc">−{{ money(quote.discount, loc) }}</dd></template>
            <template v-if="quote.money_balance_used > 0"><dt>{{ t('payments.q.balance') }}</dt><dd class="num okc">−{{ money(quote.money_balance_used, loc) }}</dd></template>
            <template v-if="quote.money_balance_used < 0"><dt>{{ t('payments.q.toBalance') }}</dt><dd class="num">+{{ money(-quote.money_balance_used, loc) }}</dd></template>
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
