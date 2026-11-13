<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiCard, UiField, UiInput, UiSegmented, UiSelect, UiSkeleton, UiSwitch } from '@/components/ui'
import { adminApi, type Rate } from '@/api/admin'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import { dmy, isoDate, money, schoolNow } from '@/utils/dates'
import { apiErr } from '@/utils/err'
import type { Locale } from '@/i18n'

type Val = boolean | number | string | Record<string, number> | null
/** Known keys in display order; unknown keys are listed after them with the raw key as the label */
const GROUPS: Record<string, string[]> = {
  attendance: ['charge_unexcused_absence', 'charge_late', 'trial_counts_in_n', 'absence_notice_hours', 'attendance_reminder_min', 'attendance_admin_alert_min', 'attendance_teacher_window', 'notify_present', 'notify_late'],
  balance: ['low_balance_lessons', 'nonpayment_block_days', 'freeze_max_days', 'freeze_max_per_course', 'left_after_days'],
  crm: ['lead_first_reply_warn_min', 'lead_stale_hours'],
  coins: ['coins'],
}
const { t, te, locale } = useI18n()
const auth = useAuthStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)
const canEdit = computed(() => auth.can('settings.edit'))
const values = ref<Record<string, Val> | null>(null)
const draft = reactive<Record<string, string>>({})
const saving = ref<string | null>(null)
const rates = ref<Rate[] | null>(null)
const rateForm = reactive({ key: '', value: '', effective_from: isoDate(schoolNow()) })
const rateErr = ref<string | null>(null)
const rateBusy = ref(false)

const label = (k: string) => (te(`settingsPage.key.${k}`) ? t(`settingsPage.key.${k}`) : k)
const hint = (k: string) => (te(`settingsPage.hint.${k}`) ? t(`settingsPage.hint.${k}`) : undefined)
const groups = computed(() => {
  const all = Object.keys(values.value ?? {})
  const known = new Set(Object.values(GROUPS).flat())
  const out = Object.entries(GROUPS).map(([g, keys]) => ({ g, keys: keys.filter((k) => all.includes(k)) }))
  const rest = all.filter((k) => !known.has(k))
  if (rest.length) out.push({ g: 'other', keys: rest })
  return out.filter((x) => x.keys.length)
})
/** attendance_teacher_window: "same_day" or hours after the lesson ends */
const WIN = 'attendance_teacher_window'
const win = reactive({ mode: 'same_day' as 'same_day' | 'hours', hours: '24' })
const winOptions = computed(() => [{ value: 'same_day' as const, label: t('settingsPage.win.sameDay') }, { value: 'hours' as const, label: t('settingsPage.win.hours') }])
const winValue = () => (win.mode === 'same_day' ? 'same_day' : Math.round(Number(win.hours)))
const winDirty = computed(() => String(winValue()) !== String(values.value?.[WIN] ?? 'same_day'))
function saveWin() {
  const v = winValue()
  if (typeof v === 'number' && !(v >= 1 && v <= 720)) return toast.error(t('settingsPage.win.invalid'))
  put(WIN, v)
}
const kind = (v: Val) => (typeof v === 'boolean' ? 'bool' : typeof v === 'number' ? 'num' : v && typeof v === 'object' ? 'obj' : 'str')

onMounted(async () => {
  const [s, r] = await Promise.all([adminApi.settings().catch(() => ({})), adminApi.rates().catch(() => [])])
  values.value = s as Record<string, Val>
  for (const [k, v] of Object.entries(values.value)) {
    if (kind(v) === 'num' || kind(v) === 'str') draft[k] = String(v ?? '')
    if (kind(v) === 'obj') for (const [sk, sv] of Object.entries(v as Record<string, number>)) draft[`${k}.${sk}`] = String(sv)
  }
  const w = values.value[WIN]
  if (typeof w === 'number' || (typeof w === 'string' && /^\d+$/.test(w))) Object.assign(win, { mode: 'hours', hours: String(w) })
  rates.value = r
  rateForm.key = r[0]?.key ?? ''
})

async function put(key: string, value: Val) {
  saving.value = key
  try {
    await adminApi.putSetting(key, value)
    if (values.value) values.value[key] = value
    toast.ok(t('settingsPage.saved', { name: label(key) }))
  } catch (e) {
    toast.error(apiErr(e) ?? t('errors.generic'))
  } finally {
    saving.value = null
  }
}
function saveScalar(key: string) {
  const v = values.value?.[key]
  if (kind(v ?? null) === 'num') {
    const n = Number(draft[key])
    if (!Number.isFinite(n) || n < 0) return toast.error(t('settingsPage.numInvalid'))
    if (n !== v) put(key, n)
  } else if (draft[key] !== v) put(key, draft[key] ?? '')
}
function saveObj(key: string) {
  const v = values.value?.[key] as Record<string, number>
  const next: Record<string, number> = {}
  for (const sk of Object.keys(v)) {
    const n = Number(draft[`${key}.${sk}`])
    if (!Number.isFinite(n) || n < 0) return toast.error(t('settingsPage.numInvalid'))
    next[sk] = Math.round(n)
  }
  put(key, next)
}
const dirty = (key: string) => {
  const v = values.value?.[key]
  if (kind(v ?? null) === 'obj') return Object.entries(v as Record<string, number>).some(([sk, sv]) => draft[`${key}.${sk}`] !== String(sv))
  return draft[key] !== String(v ?? '')
}

/** Rates grouped by key: the one in force today, the scheduled one and the history */
const today = isoDate(schoolNow())
const rateGroups = computed(() => {
  const m = new Map<string, Rate[]>()
  for (const r of rates.value ?? []) m.set(r.key, [...(m.get(r.key) ?? []), r])
  return [...m].map(([key, list]) => {
    const sorted = [...list].sort((a, b) => a.effective_from.localeCompare(b.effective_from))
    const current = [...sorted].reverse().find((r) => r.effective_from <= today) ?? null
    return { key, current, upcoming: sorted.filter((r) => r.effective_from > today), history: sorted.filter((r) => r !== current && r.effective_from <= today).reverse() }
  })
})
const rateKeys = computed(() => rateGroups.value.map((g) => ({ value: g.key, label: rateLabel(g.key) })))
const rateLabel = (k: string) => (te(`settingsPage.rate.${k}`) ? t(`settingsPage.rate.${k}`) : k)
const isMoneyRate = (k: string) => !/threshold/.test(k)

/** Inline editing: the typed value applies from today (a second change today corrects it). */
const rateDraft = reactive<Record<string, string>>({})
watch(rateGroups, (gs) => gs.forEach((g) => { if (rateDraft[g.key] === undefined) rateDraft[g.key] = String(g.current?.value ?? '') }), { immediate: true })
const rateSaving = ref<string | null>(null)
const rateDirty = (g: { key: string; current: Rate | null }) => rateDraft[g.key] !== String(g.current?.value ?? '')
async function saveRate(key: string) {
  const v = Math.round(Number(rateDraft[key]))
  if (!(v >= 0) || rateDraft[key] === '') return toast.error(t('settingsPage.numInvalid'))
  rateSaving.value = key
  try {
    const r = await adminApi.addRate({ key, value: v, effective_from: today })
    rates.value = [...(rates.value ?? []).filter((x) => !(x.key === key && x.effective_from === today)), r]
    toast.ok(t('settingsPage.rateAdded'))
  } finally {
    rateSaving.value = null
  }
}

async function addRate() {
  const v = Math.round(Number(rateForm.value))
  rateErr.value = !rateForm.key ? t('settingsPage.pickRate') : !(v >= 0) || rateForm.value === '' ? t('settingsPage.numInvalid') : rateForm.effective_from < today ? t('settingsPage.dateFuture') : null
  if (rateErr.value) return
  rateBusy.value = true
  try {
    const r = await adminApi.addRate({ key: rateForm.key, value: v, effective_from: rateForm.effective_from })
    rates.value = [...(rates.value ?? []), r]
    rateForm.value = ''
    toast.ok(t('settingsPage.rateAdded'))
  } catch (e) {
    rateErr.value = apiErr(e) ?? t('errors.generic')
  } finally {
    rateBusy.value = false
  }
}
</script>

<template>
  <div class="ph">
    <div><h1>{{ t('nav.settingsPage') }}</h1><p>{{ t('settingsPage.subtitle') }}</p></div>
    <span class="sp" />
    <UiButton v-if="auth.can('import.run')" icon="db" to="/settings/import" data-testid="open-old-crm-import">{{ t('oldCrm.open') }}</UiButton>
  </div>

  <div v-if="!values" class="grid fin-a"><div class="card card-pad"><UiSkeleton :lines="8" /></div><div class="card card-pad"><UiSkeleton :lines="8" /></div></div>
  <div v-else class="grid fin-a">
    <div class="grid" style="align-content: start; grid-template-columns: minmax(0, 1fr)">
      <UiCard v-for="g in groups" :key="g.g" :title="t(`settingsPage.group.${g.g}`)">
        <div class="set-list">
          <template v-for="k in g.keys" :key="k">
            <form v-if="k === WIN" class="set-row wrap" @submit.prevent="saveWin">
              <div class="grow"><b>{{ label(k) }}</b></div>
              <UiSegmented v-if="canEdit" v-model="win.mode" :options="winOptions" :label="label(k)" size="sm" />
              <b v-else class="num">{{ win.mode === 'same_day' ? t('settingsPage.win.sameDay') : `${win.hours} ${t('time.h')}` }}</b>
              <input v-if="canEdit && win.mode === 'hours'" v-model="win.hours" class="inp set-inp" type="number" min="1" max="720" :disabled="!canEdit" :aria-label="t('settingsPage.win.hoursLabel')" :title="t('settingsPage.win.hoursLabel')" />
              <UiButton v-if="canEdit && winDirty" type="submit" size="sm" variant="navy" :loading="saving === k">{{ t('common.save') }}</UiButton>
            </form>
            <div v-else-if="kind(values[k] ?? null) === 'bool'" class="set-row">
              <div class="grow"><b>{{ label(k) }}</b><span v-if="hint(k)">{{ hint(k) }}</span></div>
              <UiSwitch :model-value="values[k] as boolean" :label="label(k)" :disabled="!canEdit || saving === k" @update:model-value="(v: boolean) => put(k, v)" />
            </div>
            <form v-else-if="kind(values[k] ?? null) !== 'obj'" class="set-row" @submit.prevent="saveScalar(k)">
              <div class="grow"><b>{{ label(k) }}</b><span v-if="hint(k)">{{ hint(k) }}</span></div>
              <input v-model="draft[k]" class="inp set-inp" :type="kind(values[k] ?? null) === 'num' ? 'number' : 'text'" min="0" :disabled="!canEdit" :aria-label="label(k)" />
              <UiButton v-if="canEdit && dirty(k)" type="submit" size="sm" variant="navy" :loading="saving === k">{{ t('common.save') }}</UiButton>
            </form>
            <form v-else class="stack" @submit.prevent="saveObj(k)">
              <div class="set-row" v-for="(_, sk) in (values[k] as Record<string, number>)" :key="sk">
                <div class="grow"><b>{{ te(`coins.kind.${sk}`) ? t(`coins.kind.${sk}`) : sk }}</b></div>
                <input v-model="draft[`${k}.${sk}`]" class="inp set-inp" type="number" min="0" :disabled="!canEdit" :aria-label="String(sk)" />
              </div>
              <div v-if="canEdit && dirty(k)"><UiButton type="submit" size="sm" variant="navy" :loading="saving === k">{{ t('common.save') }}</UiButton></div>
            </form>
          </template>
        </div>
      </UiCard>
    </div>

    <UiCard :title="t('settingsPage.rates')">
      <UiSkeleton v-if="!rates" :lines="6" />
      <div v-else class="set-list">
        <div v-for="g in rateGroups" :key="g.key" class="set-row rate-row">
          <div class="grow">
            <b>{{ rateLabel(g.key) }}</b>
            <span v-if="g.upcoming.length">{{ g.upcoming.map((r) => t('settingsPage.from', { v: isMoneyRate(g.key) ? money(r.value, loc) : r.value, date: dmy(r.effective_from, loc) })).join('; ') }}</span>
            <span v-if="g.history.length" class="muted">{{ t('settingsPage.was', { list: g.history.slice(0, 2).map((r) => `${isMoneyRate(g.key) ? money(r.value, loc) : r.value} (${dmy(r.effective_from, loc)})`).join(', ') }) }}</span>
          </div>
          <template v-if="canEdit">
            <input v-model="rateDraft[g.key]" class="inp set-inp" type="number" min="0" inputmode="numeric" :aria-label="rateLabel(g.key)" @keydown.enter.prevent="rateDirty(g) && saveRate(g.key)" />
            <UiButton v-if="rateDirty(g)" size="sm" variant="navy" :loading="rateSaving === g.key" @click="saveRate(g.key)">{{ t('common.save') }}</UiButton>
          </template>
          <b v-else class="num">{{ g.current ? (isMoneyRate(g.key) ? money(g.current.value, loc) : g.current.value) : '—' }}</b>
        </div>
      </div>
      <form v-if="canEdit && rates?.length" class="stack subform" style="margin-top: 14px" @submit.prevent="addRate">
        <b>{{ t('settingsPage.newRateFuture') }}</b>
        <UiField :label="t('settingsPage.rateKey')"><UiSelect v-model="rateForm.key" :options="rateKeys" :label="t('settingsPage.rateKey')" block /></UiField>
        <div class="form-2">
          <UiInput v-model="rateForm.value" type="number" :min="0" :label="t('settingsPage.value')" inputmode="numeric" />
          <UiField :label="t('settingsPage.effective')"><input v-model="rateForm.effective_from" type="date" class="inp" :min="today" :aria-label="t('settingsPage.effective')" /></UiField>
        </div>
        <p v-if="rateErr" class="form-err" role="alert">{{ rateErr }}</p>
        <div><UiButton type="submit" variant="navy" :loading="rateBusy">{{ t('settingsPage.addRate') }}</UiButton></div>
      </form>
    </UiCard>
  </div>
</template>
