<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiField, UiInput, UiModal, UiSelect } from '@/components/ui'
import { booksApi, type Book } from '@/api/store'
import { useBranchStore } from '@/stores/branch'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import { apiErr } from '@/utils/err'

export type StockMode = 'receive' | 'transfer' | 'writeoff'

/** Stock movement for one book: receive from a supplier, send to another branch, or write off. */
const props = defineProps<{ book: Book | null; mode: StockMode }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ saved: [] }>()
const { t } = useI18n()
const branch = useBranchStore()
const refs = useRefsStore()
const toast = useToastStore()
const form = reactive({ branch_id: 0, to_branch_id: 0, qty: '', unit_price: '', supplier: '', reason: '' })
const error = ref<string | null>(null)
const busy = ref(false)

const mine = computed(() => branch.options.filter((o) => o.id !== null).map((o) => ({ value: o.id as number, label: o.name })))
const targets = computed(() => refs.branches.filter((b) => b.id !== form.branch_id).map((b) => ({ value: b.id, label: b.name })))
const inStock = computed(() => props.book?.stock[String(form.branch_id)]?.qty ?? 0)

watch(open, (v) => {
  if (!v) return
  refs.load()
  const first = branch.filterId ?? mine.value[0]?.value ?? 0
  Object.assign(form, { branch_id: first, to_branch_id: 0, qty: '', unit_price: props.book?.purchase_price ? String(props.book.purchase_price) : '', supplier: '', reason: '' })
  error.value = null
})
watch(() => [form.branch_id, targets.value] as const, () => {
  if (!targets.value.some((o) => o.value === form.to_branch_id)) form.to_branch_id = targets.value[0]?.value ?? 0
})

async function submit() {
  const b = props.book
  if (!b) return
  const qty = Math.round(Number(form.qty))
  error.value = !(qty > 0) ? t('books.qtyInvalid')
    : props.mode !== 'receive' && qty > inStock.value ? t('books.notEnough', { n: inStock.value })
    : props.mode === 'writeoff' && form.reason.trim().length < 3 ? t('common.reasonRequired')
    : props.mode === 'transfer' && !form.to_branch_id ? t('books.pickTarget') : null
  if (error.value) return
  busy.value = true
  try {
    if (props.mode === 'receive') {
      await booksApi.receive({ branch_id: form.branch_id, book_id: b.id, qty, unit_price: Math.max(0, Math.round(Number(form.unit_price || 0))), supplier: form.supplier.trim() || null })
      toast.ok(t('books.received', { n: qty }))
    } else if (props.mode === 'transfer') {
      await booksApi.transfer({ from_branch_id: form.branch_id, to_branch_id: form.to_branch_id, book_id: b.id, qty })
      toast.ok(t('books.sent', { n: qty, to: refs.branchName(form.to_branch_id) }))
    } else {
      await booksApi.writeoff({ branch_id: form.branch_id, book_id: b.id, qty, reason: form.reason.trim() })
      toast.ok(t('books.writtenOff', { n: qty }))
    }
    emit('saved')
    open.value = false
  } catch (e) {
    error.value = apiErr(e) ?? t('errors.generic')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiModal v-model:open="open" :title="t(`books.mode.${mode}`)">
    <form id="stock-form" class="stack" @submit.prevent="submit">
      <p v-if="book" class="m0"><b>{{ book.title }}</b></p>
      <UiField :label="mode === 'transfer' ? t('books.from') : t('branch.label')" :hint="mode !== 'receive' ? t('books.inStock', { n: inStock }) : undefined">
        <UiSelect v-model="form.branch_id" :options="mine" :label="t('branch.label')" block />
      </UiField>
      <UiField v-if="mode === 'transfer'" :label="t('books.to')"><UiSelect v-model="form.to_branch_id" :options="targets" :label="t('books.to')" block /></UiField>
      <div :class="{ 'form-2': mode === 'receive' }">
        <UiInput v-model="form.qty" type="number" :min="1" :label="t('books.qty')" inputmode="numeric" />
        <UiInput v-if="mode === 'receive'" v-model="form.unit_price" type="number" :min="0" :label="t('books.unitPrice')" inputmode="numeric" />
      </div>
      <UiInput v-if="mode === 'receive'" v-model="form.supplier" :label="t('books.supplier')" :maxlength="255" />
      <UiInput v-if="mode === 'writeoff'" v-model="form.reason" :label="t('common.reason')" :placeholder="t('books.writeoffPh')" :maxlength="255" />
      <p v-if="mode === 'transfer'" class="form-note">{{ t('books.transferNote') }}</p>
      <p v-if="mode === 'receive'" class="form-note">{{ t('books.receiveNote') }}</p>
      <p v-if="error" class="form-err" role="alert">{{ error }}</p>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton type="submit" form="stock-form" :variant="mode === 'writeoff' ? 'primary' : 'navy'" :loading="busy">{{ t(`books.do.${mode}`) }}</UiButton>
    </template>
  </UiModal>
</template>
