<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiField, UiInput, UiModal, UiSegmented, UiSelect } from '@/components/ui'
import { payrollApi } from '@/api/payroll'
import { ApiError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { useBranchStore } from '@/stores/branch'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import { periodLabel } from '@/utils/period'
import type { Locale } from '@/i18n'

/** Manual bonus / deduction / salary line for a staff member of a branch. */
const props = defineProps<{ period: string; userId?: number | null }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ saved: [] }>()
const { t, locale } = useI18n()
const auth = useAuthStore()
const branch = useBranchStore()
const refs = useRefsStore()
const toast = useToastStore()
const form = reactive({ branch_id: 0, user_id: 0, kind: 'bonus' as 'bonus' | 'deduction' | 'salary', amount: '', description: '' })
const error = ref<string | null>(null)
const busy = ref(false)

const branchOptions = computed(() => branch.options.filter((o) => o.id !== null).map((o) => ({ value: o.id as number, label: o.name })))
const people = computed(() => [{ value: 0, label: t('payroll.pickPerson') }, ...refs.staff
  .filter((s) => s.branch_ids.includes(form.branch_id) && (s.id !== auth.user?.id || auth.user?.roles.includes('owner')))
  .map((s) => ({ value: s.id, label: s.position ? `${s.full_name} · ${s.position}` : s.full_name }))])
const kinds = computed(() => (['bonus', 'deduction', 'salary'] as const).map((k) => ({ value: k, label: t(`payroll.kind.${k}`) })))

watch(open, (v) => {
  if (!v) return
  refs.loadStaff()
  error.value = null
  const mine = refs.staffById.get(props.userId ?? -1)?.branch_ids
  Object.assign(form, {
    branch_id: branch.filterId ?? (mine?.find((b) => branchOptions.value.some((o) => o.value === b)) ?? branchOptions.value[0]?.value ?? 0),
    user_id: props.userId ?? 0, kind: 'bonus', amount: '', description: '',
  })
})

async function submit() {
  const amount = Math.round(Number(form.amount))
  error.value = !form.user_id ? t('payroll.pickPerson') : !(amount > 0) ? t('fin.amountInvalid') : form.description.trim().length < 3 ? t('payroll.descRequired') : null
  if (error.value) return
  busy.value = true
  try {
    await payrollApi.adjust({ user_id: form.user_id, branch_id: form.branch_id, kind: form.kind, amount, description: form.description.trim(), period: props.period })
    toast.ok(t('payroll.adjusted'))
    emit('saved')
    open.value = false
  } catch (e) {
    error.value = e instanceof ApiError ? e.detail || t('errors.generic') : t('errors.generic')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiModal v-model:open="open" :title="t('payroll.adjustTitle', { period: periodLabel(period, locale as Locale) })">
    <form id="adj-form" class="stack" @submit.prevent="submit">
      <UiSegmented v-model="form.kind" :options="kinds" :label="t('payroll.kindLabel')" block />
      <UiField v-if="branchOptions.length > 1" :label="t('branch.label')"><UiSelect v-model="form.branch_id" :options="branchOptions" :label="t('branch.label')" block /></UiField>
      <UiField :label="t('payroll.person')"><UiSelect v-model="form.user_id" :options="people" :label="t('payroll.person')" block /></UiField>
      <UiInput v-model="form.amount" type="number" :min="1" :label="t('fin.amount')" inputmode="numeric" />
      <UiInput v-model="form.description" :label="t('payroll.desc')" :placeholder="t('payroll.descPh')" :maxlength="255" />
      <p class="form-note">{{ t('payroll.adjustNote') }}</p>
      <p v-if="error" class="form-err" role="alert">{{ error }}</p>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton :variant="form.kind === 'deduction' ? 'primary' : 'navy'" type="submit" form="adj-form" :loading="busy">{{ t(`payroll.add.${form.kind}`) }}</UiButton>
    </template>
  </UiModal>
</template>
