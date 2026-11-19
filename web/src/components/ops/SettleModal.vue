<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiField, UiInput, UiModal, UiSelect, UiSkeleton } from '@/components/ui'
import { payrollApi, type Settlement } from '@/api/payroll'
import { ApiError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { useBranchStore } from '@/stores/branch'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import { addDays, dmy, isoDate, money, schoolNow, todayIso } from '@/utils/dates'
import { periodLabel } from '@/utils/period'
import type { Locale } from '@/i18n'

/** «Рассчитаться»: pick a staff member, see what is earned by part of the pay (оклад, ставка, KPI…), tick what
 * is paid now, add a bonus or a fine, pay. More than earned may be paid: the rest is the person's debt. */
const props = defineProps<{ period: string; userId?: number | null }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ saved: [] }>()
const { t, locale } = useI18n()
const loc = computed(() => locale.value as Locale)
const auth = useAuthStore()
const branch = useBranchStore()
const refs = useRefsStore()
const toast = useToastStore()

const form = reactive({ branch_id: 0, user_id: 0, paid_on: '', bonus: '', bonusNote: '', fine: '', fineNote: '' })
const data = ref<Settlement | null>(null)
const loading = ref(false)
const pick = reactive<Record<string, { on: boolean; amount: string }>>({})
const error = ref<string | null>(null)
const busy = ref(false)

const branchOptions = computed(() => branch.options.filter((o) => o.id !== null).map((o) => ({ value: o.id as number, label: o.name })))
const people = computed(() => [{ value: 0, label: t('payroll.pickPerson') }, ...refs.staff
  .filter((s) => s.branch_ids.includes(form.branch_id) && (s.id !== auth.user?.id || auth.user?.roles.includes('owner')))
  .map((s) => ({ value: s.id, label: s.position ? `${s.full_name} · ${s.position}` : s.full_name }))])
const minDay = computed(() => isoDate(addDays(schoolNow(), -31)))

watch(open, (v) => {
  if (!v) return
  refs.loadStaff()
  error.value = null
  data.value = null
  const mine = refs.staffById.get(props.userId ?? -1)?.branch_ids
  Object.assign(form, {
    branch_id: branch.filterId ?? (mine?.find((b) => branchOptions.value.some((o) => o.value === b)) ?? branchOptions.value[0]?.value ?? 0),
    user_id: props.userId ?? 0, paid_on: todayIso(), bonus: '', bonusNote: '', fine: '', fineNote: '',
  })
  load()
})

function fill(s: Settlement) {
  data.value = s
  for (const p of s.parts) pick[p.part] = { on: p.left !== 0, amount: p.left !== 0 ? String(p.left) : '' }
}
async function load() {
  data.value = null
  if (!form.user_id || !form.branch_id) return
  loading.value = true
  const key = `${form.user_id}|${form.branch_id}`
  try {
    const s = await payrollApi.settlement({ user_id: form.user_id, branch_id: form.branch_id, period: props.period })
    if (key === `${form.user_id}|${form.branch_id}`) fill(s)
  } catch (e) {
    error.value = e instanceof ApiError ? e.detail || t('errors.generic') : t('errors.generic')
  } finally {
    loading.value = false
  }
}
watch(() => [form.user_id, form.branch_id], () => open.value && ((error.value = null), load()))
watch(() => form.branch_id, () => !people.value.some((p) => p.value === form.user_id) && (form.user_id = 0))

/** Rows worth showing: the two main parts always, the others when there is something in them. */
const rows = computed(() => (data.value?.parts ?? []).filter((p) => ['salary', 'rate', 'kpi'].includes(p.part) || p.accrued !== 0 || p.left !== 0 || p.paid !== 0))
const num = (v: string) => Math.round(Number(v) || 0)
const lines = computed(() => rows.value.filter((p) => pick[p.part]?.on && num(pick[p.part]!.amount) !== 0).map((p) => ({ part: p.part, amount: num(pick[p.part]!.amount) })))
const bonus = computed(() => Math.max(0, num(form.bonus)))
const fine = computed(() => Math.max(0, num(form.fine)))
const total = computed(() => lines.value.reduce((s, l) => s + l.amount, 0) + bonus.value - fine.value)
/** What is still owed after this payment; below zero = the person's debt. */
const after = computed(() => (data.value?.balance ?? 0) - lines.value.reduce((s, l) => s + l.amount, 0))

async function submit() {
  error.value = !form.user_id ? t('payroll.pickPerson')
    : bonus.value && form.bonusNote.trim().length < 3 ? t('nv.settle.bonusNote')
      : fine.value && form.fineNote.trim().length < 3 ? t('nv.settle.fineNote')
        : !lines.value.length && !bonus.value && !fine.value ? t('nv.settle.nothing')
          : total.value < 0 ? t('nv.settle.negative') : null
  if (error.value) return
  busy.value = true
  try {
    fill(await payrollApi.payOut({
      user_id: form.user_id, branch_id: form.branch_id, period: props.period, paid_on: form.paid_on || null, lines: lines.value,
      bonus: bonus.value ? { amount: bonus.value, note: form.bonusNote.trim() } : null,
      fine: fine.value ? { amount: fine.value, note: form.fineNote.trim() } : null,
    }))
    Object.assign(form, { bonus: '', bonusNote: '', fine: '', fineNote: '' })
    toast.ok(t('nv.settle.done'))
    emit('saved')
  } catch (e) {
    error.value = e instanceof ApiError ? e.detail || t('errors.generic') : t('errors.generic')
  } finally {
    busy.value = false
  }
}
async function cancel(id: number) {
  busy.value = true
  try {
    await payrollApi.cancelPayout(id)
    toast.ok(t('nv.settle.cancelled'))
    emit('saved')
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.detail || t('errors.generic') : t('errors.generic')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiModal v-model:open="open" :title="t('nv.settle.title', { period: periodLabel(period, loc) })">
    <form id="settle-form" class="stack" @submit.prevent="submit">
      <UiField v-if="branchOptions.length > 1" :label="t('branch.label')"><UiSelect v-model="form.branch_id" :options="branchOptions" :label="t('branch.label')" block /></UiField>
      <UiField :label="t('payroll.person')"><UiSelect v-model="form.user_id" :options="people" :label="t('payroll.person')" block /></UiField>
      <UiSkeleton v-if="loading" :lines="4" />
      <template v-else-if="data">
        <div class="st-rows">
          <label v-for="p in rows" :key="p.part" class="st-row" :class="{ off: !pick[p.part]!.on }">
            <input v-model="pick[p.part]!.on" type="checkbox" />
            <span class="grow">
              <b>{{ p.title }}</b>
              <span class="muted">{{ t('nv.settle.accrued') }} {{ money(p.accrued, loc) }}<template v-if="p.note"> · {{ p.note }}</template><template v-if="p.paid"> · {{ t('nv.settle.paid') }} {{ money(p.paid, loc) }}</template></span>
            </span>
            <input v-model="pick[p.part]!.amount" class="st-sum num" type="number" inputmode="numeric" :disabled="!pick[p.part]!.on" :aria-label="`${p.title}: ${t('fin.amount')}`" />
          </label>
        </div>
        <div class="form-2">
          <UiInput v-model="form.bonus" type="number" inputmode="numeric" :min="0" :label="t('nv.settle.bonus')" />
          <UiInput v-model="form.bonusNote" :label="t('nv.settle.forWhat')" :maxlength="255" />
        </div>
        <div class="form-2">
          <UiInput v-model="form.fine" type="number" inputmode="numeric" :min="0" :label="t('nv.settle.fine')" />
          <UiInput v-model="form.fineNote" :label="t('nv.settle.forWhat')" :maxlength="255" />
        </div>
        <UiInput v-model="form.paid_on" type="date" :min="minDay" :max="todayIso()" :label="t('nv.settle.date')" />
        <div class="st-total">
          <span class="grow"><b>{{ t('nv.settle.toPay') }}</b><span class="muted">{{ after < 0 ? t('nv.settle.debtAfter', { sum: money(-after, loc) }) : t('nv.settle.leftAfter', { sum: money(after, loc) }) }}</span></span>
          <b class="num st-big" :class="{ redc: total < 0 }">{{ money(total, loc) }}</b>
        </div>
        <template v-if="data.payouts.length">
          <h4 class="m0">{{ t('nv.settle.history') }}</h4>
          <div class="lr-list">
            <div v-for="x in data.payouts" :key="x.id" class="list-row">
              <div class="grow"><b class="num">{{ dmy(x.paid_on, loc) }} · {{ money(x.total, loc) }}</b><span>{{ x.lines.map((l) => `${l.title} ${money(l.amount, loc)}`).join(', ') }}</span></div>
              <UiButton size="sm" variant="ghost" :disabled="busy" @click="cancel(x.id)">{{ t('nv.settle.cancel') }}</UiButton>
            </div>
          </div>
        </template>
      </template>
      <p v-if="error" class="form-err" role="alert">{{ error }}</p>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.close') }}</UiButton>
      <UiButton variant="primary" icon="wallet" type="submit" form="settle-form" :loading="busy" :disabled="!data">{{ t('nv.settle.pay') }}</UiButton>
    </template>
  </UiModal>
</template>

<style scoped>
.st-rows { display: flex; flex-direction: column; border: 1px solid var(--line); border-radius: 12px; overflow: hidden }
.st-row { display: flex; align-items: center; gap: 10px; padding: 10px 12px; cursor: pointer; background: var(--surface) }
.st-row + .st-row { border-top: 1px solid var(--line) }
.st-row .grow { display: flex; flex-direction: column; min-width: 0; font-size: 13.5px }
.st-row .grow span { font-size: 12px }
.st-row.off b { color: var(--muted) }
.st-row input[type=checkbox] { width: 18px; height: 18px; accent-color: var(--btn-navy); flex: 0 0 auto }
.st-sum { width: 120px; flex: 0 0 auto; text-align: right; border: 1px solid var(--line); border-radius: 8px; padding: 7px 9px; font: inherit; font-weight: 600; background: var(--surface); color: inherit }
.st-sum:disabled { opacity: .45 }
.st-total { display: flex; align-items: center; gap: 10px; border-top: 1px solid var(--line); padding-top: 12px }
.st-total .grow { display: flex; flex-direction: column; font-size: 13.5px }
.st-total .grow span { font-size: 12px }
.st-big { font-size: 20px }
</style>
