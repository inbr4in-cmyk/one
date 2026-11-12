<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiField, UiIcon, UiInput, UiModal, UiSelect } from '@/components/ui'
import { shopApi, type ShopItem } from '@/api/store'
import { useAuthStore } from '@/stores/auth'
import { useBranchStore } from '@/stores/branch'
import { useToastStore } from '@/stores/toast'
import { apiErr } from '@/utils/err'

const SHOP_ICONS = ['gift', 'cup', 'shirt', 'bag', 'book', 'star', 'trophy', 'medal', 'notebook', 'pencil', 'head', 'zap']

/** Create or edit a coin-shop item (shop.edit). Cost is our purchase price; it lands in expenses when the item is issued. */
const props = defineProps<{ item: ShopItem | null }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ saved: [] }>()
const { t } = useI18n()
const auth = useAuthStore()
const branch = useBranchStore()
const toast = useToastStore()
const form = reactive({ name: '', icon: 'gift', price_coins: '', stock: '', cost: '', branch_id: 0 })
const error = ref<string | null>(null)
const busy = ref(false)
const network = computed(() => auth.can('shop.edit', 'network'))
const branches = computed(() => [...(network.value ? [{ value: 0, label: t('shop.allBranches') }] : []), ...branch.options.filter((o) => o.id !== null).map((o) => ({ value: o.id as number, label: o.name }))])

watch(open, (v) => {
  if (!v) return
  const i = props.item
  Object.assign(form, {
    name: i?.name ?? '', icon: i?.icon ?? 'gift', price_coins: i ? String(i.price_coins) : '', stock: i ? String(i.stock) : '',
    cost: i?.cost != null ? String(i.cost) : '', branch_id: i?.branch_id ?? (network.value ? 0 : branch.filterId ?? branches.value[0]?.value ?? 0),
  })
  error.value = null
})

async function submit() {
  const price = Math.round(Number(form.price_coins))
  const stock = Math.round(Number(form.stock || 0))
  const cost = Math.round(Number(form.cost || 0))
  error.value = form.name.trim().length < 2 ? t('shop.nameRequired') : !(price > 0) ? t('shop.priceInvalid') : stock < 0 || cost < 0 ? t('books.qtyInvalid') : null
  if (error.value) return
  busy.value = true
  try {
    const body = { name: form.name.trim(), icon: form.icon, price_coins: price, stock, cost, branch_id: form.branch_id || null }
    await (props.item ? shopApi.update(props.item.id, body) : shopApi.create(body))
    toast.ok(props.item ? t('common.saved') : t('shop.created'))
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
  <UiModal v-model:open="open" :title="item ? t('shop.editTitle') : t('shop.newTitle')">
    <form id="shop-form" class="stack" @submit.prevent="submit">
      <UiInput v-model="form.name" :label="t('shop.name')" :placeholder="t('shop.namePh')" :maxlength="255" />
      <UiField :label="t('shop.icon')">
        <div class="ico-pick" role="radiogroup" :aria-label="t('shop.icon')">
          <button v-for="i in SHOP_ICONS" :key="i" type="button" role="radio" :aria-checked="form.icon === i" :class="{ on: form.icon === i }" @click="form.icon = i"><UiIcon :name="i" /></button>
        </div>
      </UiField>
      <div class="form-2">
        <UiInput v-model="form.price_coins" type="number" :min="1" :label="t('shop.price')" inputmode="numeric" />
        <UiInput v-model="form.stock" type="number" :min="0" :label="t('shop.stock')" inputmode="numeric" />
      </div>
      <div class="form-2">
        <UiInput v-model="form.cost" type="number" :min="0" :label="t('shop.cost')" inputmode="numeric" />
        <UiField :label="t('branch.label')"><UiSelect v-model="form.branch_id" :options="branches" :label="t('branch.label')" block /></UiField>
      </div>
      <p v-if="error" class="form-err" role="alert">{{ error }}</p>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton type="submit" form="shop-form" variant="navy" :loading="busy">{{ item ? t('common.save') : t('shop.create') }}</UiButton>
    </template>
  </UiModal>
</template>
