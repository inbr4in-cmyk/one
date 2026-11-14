<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiField, UiInput, UiModal, UiSegmented, UiSelect } from '@/components/ui'
import { booksApi, type Book } from '@/api/store'
import { PAYMENT_METHODS, type PaymentMethod } from '@/api/payments'
import { useToastStore } from '@/stores/toast'
import { money } from '@/utils/dates'
import { apiErr } from '@/utils/err'
import type { Locale } from '@/i18n'

/** Sell a book to a student from their branch stock; the sale becomes a separate «Книги» payment. */
const props = defineProps<{ student: { id: number; full_name: string; branch_id: number }; neededIds?: number[]; fromPayment?: boolean; available?: number }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ sold: [] }>()
const { t, locale } = useI18n()
const toast = useToastStore()
const books = ref<Book[] | null>(null)
const bookId = ref(0)
const qty = ref('1')
const method = ref<PaymentMethod>('kaspi')
const error = ref<string | null>(null)
const busy = ref(false)

const stockOf = (b: Book) => b.stock[String(props.student.branch_id)]?.qty ?? 0
const options = computed(() => {
  const list = [...(books.value ?? [])].sort((a, b) => Number(props.neededIds?.includes(b.id)) - Number(props.neededIds?.includes(a.id)))
  return list.map((b) => ({ value: b.id, label: `${b.title} · ${money(b.sale_price, locale.value as Locale)} · ${t('books.left', { n: stockOf(b) })}` }))
})
const book = computed(() => books.value?.find((b) => b.id === bookId.value))
const total = computed(() => (book.value?.sale_price ?? 0) * Math.max(0, Math.round(Number(qty.value) || 0)))
const methods = computed(() => PAYMENT_METHODS.map((m) => ({ value: m, label: t(`payments.method.${m}`) })))

watch(open, async (v) => {
  if (!v) return
  error.value = null
  qty.value = '1'
  books.value = null
  books.value = await booksApi.list(props.student.branch_id).catch(() => [])
  bookId.value = props.neededIds?.find((id) => books.value?.some((b) => b.id === id)) ?? books.value[0]?.id ?? 0
})

async function submit() {
  const n = Math.round(Number(qty.value))
  error.value = !book.value ? t('books.pickBook') : !(n > 0) ? t('books.qtyInvalid') : n > stockOf(book.value) ? t('books.notEnough', { n: stockOf(book.value) }) : null
  if (!error.value && props.fromPayment && total.value > (props.available ?? 0)) error.value = t('nv.book.notEnough', { sum: money(props.available ?? 0, locale.value as Locale) })
  if (error.value) return
  busy.value = true
  try {
    const r = await booksApi.sell({ student_id: props.student.id, book_id: bookId.value, method: method.value, qty: n, from_payment: !!props.fromPayment })
    toast.ok(t('books.sold', { sum: money(r.amount, locale.value as Locale), n: r.left_in_stock }))
    emit('sold')
    open.value = false
  } catch (e) {
    error.value = apiErr(e) ?? t('errors.generic')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiModal v-model:open="open" :title="t('books.sellTitle', { name: student.full_name })">
    <form id="sell-form" class="stack" @submit.prevent="submit">
      <UiField :label="t('books.book')"><UiSelect v-model="bookId" :options="options" :label="t('books.book')" :disabled="!books" block /></UiField>
      <UiInput v-model="qty" type="number" :min="1" :label="t('books.qty')" inputmode="numeric" />
      <UiField v-if="!fromPayment" :label="t('payments.methodLabel')"><UiSegmented v-model="method" :options="methods" :label="t('payments.methodLabel')" size="sm" class="wrap" /></UiField>
      <div v-else class="alert info"><span>{{ t('nv.book.fromPaymentInfo', { sum: money(available ?? 0, locale as Locale) }) }}</span></div>
      <div class="sum-line"><span>{{ fromPayment ? t('nv.book.fromPaymentSum') : t('books.toPay') }}</span><b class="num">{{ money(total, locale as Locale) }}</b></div>
      <p v-if="error" class="form-err" role="alert">{{ error }}</p>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton type="submit" form="sell-form" variant="primary" icon="wallet" :loading="busy" :disabled="!book">{{ fromPayment ? t('nv.book.fromPayment') : t('books.sell') }}</UiButton>
    </template>
  </UiModal>
</template>
