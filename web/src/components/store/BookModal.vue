<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiField, UiInput, UiModal, UiSelect } from '@/components/ui'
import { booksApi, type Book } from '@/api/store'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import { apiErr } from '@/utils/err'

/** Create or edit a catalog book (books.edit). */
const props = defineProps<{ book: Book | null }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ saved: [] }>()
const { t } = useI18n()
const refs = useRefsStore()
const toast = useToastStore()
const form = reactive({ title: '', level_id: 0, sale_price: '', purchase_price: '' })
const error = ref<string | null>(null)
const busy = ref(false)
const levels = computed(() => [{ value: 0, label: t('books.noLevel') }, ...refs.levels.map((l) => ({ value: l.id, label: l.name }))])

watch(open, (v) => {
  if (!v) return
  refs.load()
  const b = props.book
  Object.assign(form, { title: b?.title ?? '', level_id: b?.level_id ?? 0, sale_price: b ? String(b.sale_price) : '', purchase_price: b?.purchase_price != null ? String(b.purchase_price) : '' })
  error.value = null
})

async function submit() {
  const sale = Math.round(Number(form.sale_price))
  const buy = Math.round(Number(form.purchase_price || 0))
  error.value = form.title.trim().length < 2 ? t('books.titleRequired') : !(sale > 0) || buy < 0 ? t('books.priceInvalid') : null
  if (error.value) return
  busy.value = true
  try {
    const body = { title: form.title.trim(), level_id: form.level_id || null, sale_price: sale, purchase_price: buy }
    await (props.book ? booksApi.update(props.book.id, body) : booksApi.create(body))
    toast.ok(props.book ? t('common.saved') : t('books.created'))
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
  <UiModal v-model:open="open" :title="book ? t('books.editTitle') : t('books.newTitle')">
    <form id="book-form" class="stack" @submit.prevent="submit">
      <UiInput v-model="form.title" :label="t('books.titleLabel')" :placeholder="t('books.titlePh')" :maxlength="255" />
      <UiField :label="t('books.level')"><UiSelect v-model="form.level_id" :options="levels" :label="t('books.level')" block /></UiField>
      <div class="form-2">
        <UiInput v-model="form.sale_price" type="number" :min="1" :label="t('books.salePrice')" inputmode="numeric" />
        <UiInput v-model="form.purchase_price" type="number" :min="0" :label="t('books.purchasePrice')" inputmode="numeric" />
      </div>
      <p v-if="error" class="form-err" role="alert">{{ error }}</p>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton type="submit" form="book-form" variant="navy" :loading="busy">{{ book ? t('common.save') : t('books.create') }}</UiButton>
    </template>
  </UiModal>
</template>
