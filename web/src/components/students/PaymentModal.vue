<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiField, UiInput, UiModal, UiSegmented, UiSelect, UiSkeleton, UiTextarea } from '@/components/ui'
import { useRefsStore } from '@/stores/refs'
import { packagesApi, paymentsApi, PAYMENT_METHODS, type PaymentMethod, type Quote, type SubscriptionPackage } from '@/api/payments'
import type { Student } from '@/api/students'
import { ApiError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import { money } from '@/utils/dates'
import type { Locale } from '@/i18n'

type By = 'amount' | 'lessons' | 'package'
const props = defineProps<{ student: Student; mode?: By }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ paid: [] }>()
const { t, locale } = useI18n()
const auth = useAuthStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)
const refs = useRefsStore()
/** A student without a level (e.g. imported from the old CRM) needs one to price the lessons: chosen here. */
const needLevel = computed(() => !props.student.level_id && form.by !== 'package')
const levelPick = ref(0)
const levelOptions = computed(() => [{ value: 0, label: t('payments.pickLevel') }, ...refs.levels.map((l) => ({ value: l.id, label: l.lesson_price ? `${l.name} · ${money(l.lesson_price, loc.value)}` : l.name }))])

const PACKS = [8, 12, 24]
const todayIso = () => { const d = new Date(); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10) }
const form = reactive({ by: (props.mode ?? 'amount') as By, lessons: '12', amount: '', method: 'kaspi' as PaymentMethod, discount: '', promo: '', note: '', paid_on: todayIso() })
const byOptions = computed(() => [
  { value: 'amount' as By, label: t('payments.byAmount') },
  { value: 'lessons' as By, label: t('payments.byLessons') },
  { value: 'package' as By, label: t('payments.byPackage') },
])
/** Subscriptions (абонементы) from the Справочники page */
const packages = ref<SubscriptionPackage[] | null>(null)
const pkgId = ref(0)
const byPackage = computed(() => form.by === 'package')
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
  level_id: needLevel.value && levelPick.value ? levelPick.value : null,
  lessons: byAmount.value || byPackage.value ? 0 : lessons.value,
  amount: byAmount.value ? amount.value : null,
  package_id: byPackage.value && pkgId.value ? pkgId.value : null,
  method: form.method,
  discount: !byAmount.value && auth.can('payments.discount') ? Math.max(0, Number(form.discount) || 0) : 0,
  promo_code: form.promo.trim() || null,
  note: form.note.trim() || null,
  paid_on: backdated.value ? form.paid_on : null,
}))

watch(open, (v) => {
  if (!v) return
  Object.assign(form, { by: props.mode ?? 'amount', lessons: '12', amount: '', method: 'kaspi', discount: '', promo: '', note: '', paid_on: todayIso() })
  levelPick.value = 0
  pkgId.value = 0
  quote.value = null
  packagesApi.list().then((list) => {
    packages.value = list
    if (list.length === 1) pkgId.value = list[0]!.id
  }).catch(() => (packages.value = []))
})

let timer: ReturnType<typeof setTimeout> | undefined
watch([open, () => JSON.stringify({ ...body.value, method: '', note: '', paid_on: '' })], () => {
  if (!open.value) return
  clearTimeout(timer)
  timer = setTimeout(fetchQuote, 250)
})

async function fetchQuote() {
  if (byPackage.value && !pkgId.value) {
    quote.value = null
    quoteError.value = packages.value && !packages.value.length ? t('payments.noPackages') : t('payments.pickPackage')
    return
  }
  if (needLevel.value && !levelPick.value) {
    quote.value = null
    quoteError.value = t('payments.pickLevelFirst')
    return
  }
  if (!byPackage.value && (byAmount.value ? amount.value < 1 : lessons.value < 1)) {
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
      <UiField v-if="needLevel" :label="t('students.form.level')">
        <UiSelect v-model="levelPick" :options="levelOptions" :label="t('students.form.level')" block />
      </UiField>
      <UiSegmented v-model="form.by" :options="byOptions" :label="t('payments.byLabel')" size="sm" />
      <UiInput v-if="byAmount" v-model="form.amount" type="number" inputmode="numeric" :min="1" :label="t('payments.amount')"
        :hint="t('payments.amountHint')" autofocus />
      <div v-else-if="byPackage" class="pkg-list" role="radiogroup" :aria-label="t('payments.byPackage')">
        <button v-for="p in packages ?? []" :key="p.id" type="button" role="radio" class="pkg" :aria-checked="pkgId === p.id" @click="pkgId = p.id">
          <b>{{ p.name }}</b><span class="num">{{ money(p.price, loc) }}</span><small>{{ t('payments.pkgInfo', { m: p.months, n: p.lessons }) }}</small>
        </button>
        <UiSkeleton v-if="!packages" :lines="2" />
      </div>
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
            <template v-if="byPackage"><dt>{{ t('payments.byPackage') }}</dt><dd>{{ packages?.find((p) => p.id === pkgId)?.name }} · {{ t('students.nLessons', { n: quote.lessons }) }}</dd></template>
            <template v-else><dt>{{ t('payments.q.price') }}</dt><dd class="num">{{ money(quote.lesson_price, loc) }} × {{ quote.lessons }}</dd></template>
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

<style scoped>
.pkg-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px }
.pkg { display: grid; gap: 2px; text-align: left; padding: 10px 12px; border: 1px solid var(--line); border-radius: 10px; background: var(--surface); font: inherit; color: inherit; cursor: pointer }
.pkg span { font-weight: 700; color: var(--accent-ink) }
.pkg small { color: var(--muted) }
.pkg[aria-checked="true"] { border-color: var(--btn-navy); box-shadow: 0 0 0 2px var(--btn-navy) inset }
</style>
