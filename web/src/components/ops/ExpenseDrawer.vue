<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiCheck, UiDrawer, UiField, UiInput, UiSelect } from '@/components/ui'
import { financeApi, type Expense, type ExpenseCategory } from '@/api/finance'
import { ApiError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { useBranchStore } from '@/stores/branch'
import { useToastStore } from '@/stores/toast'
import { isoDate } from '@/utils/dates'

/** Create or edit an expense. Network-wide (shared) expenses are only for network-scope finance editors. */
const props = defineProps<{ expense?: Expense | null; categories: ExpenseCategory[] }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ saved: []; categoryAdded: [ExpenseCategory] }>()
const { t } = useI18n()
const auth = useAuthStore()
const branch = useBranchStore()
const toast = useToastStore()

const NETWORK = -1
const form = reactive({ branch_id: 0, category_id: 0, amount: '', spent_on: '', note: '', recurring: false, recurring_day: '1' })
const newCat = reactive({ open: false, name: '', code: '' })
const errors = reactive<Record<string, string | null>>({})
const busy = ref(false)

const canNetwork = computed(() => auth.can('finance.edit', 'network'))
const branchOptions = computed(() => [
  ...branch.options.filter((o) => o.id !== null).map((o) => ({ value: o.id as number, label: o.name })),
  ...(canNetwork.value ? [{ value: NETWORK, label: t('fin.networkExpense') }] : []),
])
const catOptions = computed(() => [{ value: 0, label: t('fin.pickCategory') }, ...props.categories.map((c) => ({ value: c.id, label: c.name }))])

watch(open, (v) => {
  if (!v) return
  Object.keys(errors).forEach((k) => (errors[k] = null))
  newCat.open = false
  const e = props.expense
  Object.assign(form, e
    ? { branch_id: e.branch_id ?? NETWORK, category_id: e.category_id, amount: String(e.amount), spent_on: e.spent_on, note: e.note ?? '', recurring: e.recurring, recurring_day: String(e.recurring_day ?? 1) }
    : { branch_id: branch.filterId ?? branchOptions.value[0]?.value ?? 0, category_id: 0, amount: '', spent_on: isoDate(new Date()), note: '', recurring: false, recurring_day: '1' })
})

async function addCategory() {
  errors.cat = null
  const name = newCat.name.trim()
  const code = newCat.code.trim().toLowerCase()
  if (name.length < 2 || !/^[a-z0-9_]{2,32}$/.test(code)) {
    errors.cat = t('fin.catInvalid')
    return
  }
  try {
    const c = await financeApi.createCategory({ name, code })
    emit('categoryAdded', c)
    form.category_id = c.id
    Object.assign(newCat, { open: false, name: '', code: '' })
  } catch (e) {
    errors.cat = e instanceof ApiError ? e.detail : t('errors.generic')
  }
}

async function submit() {
  Object.keys(errors).forEach((k) => (errors[k] = null))
  const amount = Math.round(Number(form.amount))
  if (!form.category_id) errors.category = t('fin.pickCategory')
  if (!amount || amount <= 0) errors.amount = t('fin.amountInvalid')
  if (!form.spent_on) errors.spent_on = t('fin.dateRequired')
  const day = Number(form.recurring_day)
  if (form.recurring && !(day >= 1 && day <= 28)) errors.day = t('fin.dayInvalid')
  if (Object.values(errors).some(Boolean)) return
  busy.value = true
  const body = {
    branch_id: form.branch_id === NETWORK ? null : form.branch_id, category_id: form.category_id, amount, spent_on: form.spent_on,
    note: form.note.trim() || null, recurring: form.recurring, recurring_day: form.recurring ? day : null,
  }
  try {
    if (props.expense) await financeApi.updateExpense(props.expense.id, body)
    else await financeApi.createExpense(body)
    toast.ok(props.expense ? t('common.saved') : t('fin.expenseAdded'))
    emit('saved')
    open.value = false
  } catch (e) {
    errors.form = e instanceof ApiError ? e.detail || t('errors.generic') : t('errors.generic')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiDrawer v-model:open="open" :title="expense ? t('fin.editExpense') : t('fin.newExpense')">
    <form id="exp-form" class="stack" novalidate @submit.prevent="submit">
      <UiField :label="t('branch.label')"><UiSelect v-model="form.branch_id" :options="branchOptions" :label="t('branch.label')" block /></UiField>
      <UiField :label="t('fin.category')" :error="errors.category">
        <UiSelect v-model="form.category_id" :options="catOptions" :label="t('fin.category')" block />
      </UiField>
      <button v-if="auth.can('finance.edit') && !newCat.open" type="button" class="linkbtn" style="align-self: flex-start" @click="newCat.open = true">{{ t('fin.addCategory') }}</button>
      <div v-if="newCat.open" class="subform">
        <div class="form-2">
          <UiInput v-model="newCat.name" :label="t('fin.catName')" :placeholder="t('fin.catNamePh')" />
          <UiInput v-model="newCat.code" :label="t('fin.catCode')" placeholder="rent" :hint="t('fin.catCodeHint')" />
        </div>
        <p v-if="errors.cat" class="form-err" role="alert">{{ errors.cat }}</p>
        <div class="row-acts"><UiButton size="sm" @click="newCat.open = false">{{ t('common.cancel') }}</UiButton><UiButton size="sm" variant="navy" @click="addCategory">{{ t('common.add') }}</UiButton></div>
      </div>
      <div class="form-2">
        <UiInput v-model="form.amount" type="number" :min="1" :label="t('fin.amount')" :error="errors.amount" inputmode="numeric" />
        <UiInput v-model="form.spent_on" type="date" :label="t('fin.spentOn')" :error="errors.spent_on" />
      </div>
      <UiInput v-model="form.note" :label="t('fin.note')" :placeholder="t('fin.notePh')" :maxlength="255" />
      <UiCheck v-model="form.recurring" :label="t('fin.recurring')" :hint="t('fin.recurringHint')" />
      <UiInput v-if="form.recurring" v-model="form.recurring_day" type="number" :min="1" :max="28" :label="t('fin.recurringDay')" :error="errors.day" />
      <p v-if="errors.form" class="form-err" role="alert">{{ errors.form }}</p>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="primary" type="submit" form="exp-form" :loading="busy">{{ expense ? t('common.save') : t('common.add') }}</UiButton>
    </template>
  </UiDrawer>
</template>
