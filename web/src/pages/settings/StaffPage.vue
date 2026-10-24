<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiAvatar, UiButton, UiCard, UiChip, UiEmptyState, UiIcon, UiInput, UiModal, UiPager, UiPrompt, UiSkeleton, UiTabs } from '@/components/ui'
import StaffDrawer from '@/components/admin/StaffDrawer.vue'
import { adminApi, type Role, type Staff } from '@/api/admin'
import { workApi, type CheckinRow, type DailyReport } from '@/api/staffwork'
import { useAuthStore } from '@/stores/auth'
import { useBranchStore } from '@/stores/branch'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import { addDays, hm, isoDate } from '@/utils/dates'
import { relativeTime } from '@/utils/format'
import { apiErr } from '@/utils/err'
import { formatPhone } from '@/utils/phone'
import type { Locale } from '@/i18n'

type Tab = 'list' | 'checkins' | 'reports'
const LIMIT = 30
const { t, te, locale } = useI18n()
const auth = useAuthStore()
const branch = useBranchStore()
const refs = useRefsStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)

const tab = ref<Tab>('list')
const tabs = computed(() => [
  { value: 'list' as const, label: t('staff.tab.list') },
  { value: 'checkins' as const, label: t('staff.tab.checkins') },
  { value: 'reports' as const, label: t('staff.tab.reports') },
])
const q = ref('')
const archived = ref(false)
const offset = ref(0)
const page = ref<{ items: Staff[]; total: number } | null>(null)
const roles = ref<Role[]>([])
const drawer = ref(false)
const editing = ref<Staff | null>(null)
const pwFor = ref<Staff | null>(null)
const pw = ref('')
const pwErr = ref<string | null>(null)
const confirmFor = ref<{ s: Staff; kind: 'archive' | 'reset2fa' } | null>(null)
const busy = ref(false)
const day = ref(isoDate(new Date()))
const checkins = ref<CheckinRow[] | null>(null)
const reports = ref<DailyReport[] | null>(null)

let seq = 0
async function loadStaff() {
  const my = ++seq
  page.value = null
  const r = await adminApi.staff({ q: q.value.trim() || undefined, branch_id: branch.filterId, archived: archived.value || undefined, limit: LIMIT, offset: offset.value }).catch(() => ({ items: [], total: 0 }))
  if (my === seq) page.value = r
}
let timer: ReturnType<typeof setTimeout> | undefined
watch(q, () => {
  clearTimeout(timer)
  timer = setTimeout(() => (offset.value === 0 ? loadStaff() : (offset.value = 0)), 250)
})
watch([archived, () => branch.filterId], () => (offset.value === 0 ? loadStaff() : (offset.value = 0)))
watch(offset, loadStaff)
async function loadDay() {
  if (tab.value === 'checkins') {
    checkins.value = null
    checkins.value = await workApi.checkins({ day: day.value, branch_id: branch.filterId }).catch(() => [])
  } else if (tab.value === 'reports') {
    reports.value = null
    reports.value = await workApi.reports(day.value).catch(() => [])
  }
}
watch([tab, day, () => branch.filterId], loadDay)
onMounted(async () => {
  refs.load()
  loadStaff()
  if (auth.can('roles.view')) roles.value = await adminApi.roles().catch(() => [])
})

function openNew() {
  editing.value = null
  drawer.value = true
}
function edit(s: Staff) {
  editing.value = s
  drawer.value = true
}
async function setPassword() {
  const s = pwFor.value
  if (!s) return
  busy.value = true
  pwErr.value = null
  try {
    await adminApi.setPassword(s.id, pw.value)
    toast.ok(t('staff.passwordSet'))
    pwFor.value = null
  } catch (e) {
    pwErr.value = apiErr(e) ?? t('errors.generic')
  } finally {
    busy.value = false
  }
}
async function confirmAction() {
  const c = confirmFor.value
  if (!c) return
  busy.value = true
  try {
    if (c.kind === 'archive') await adminApi.archiveStaff(c.s.id)
    else await adminApi.reset2fa(c.s.id)
    toast.ok(c.kind === 'archive' ? t('staff.archived') : t('staff.twoFaReset'))
    confirmFor.value = null
    loadStaff()
  } catch (e) {
    toast.error(apiErr(e) ?? t('errors.generic'))
  } finally {
    busy.value = false
  }
}
const isOwner = computed(() => !!auth.user?.roles.includes('owner'))
const dayLabelText = computed(() => (day.value === isoDate(new Date()) ? t('staff.today') : day.value))
const hours = (r: CheckinRow) => {
  const end = r.out_at ? new Date(r.out_at) : new Date()
  const h = (end.getTime() - new Date(r.in_at).getTime()) / 3600000
  return `${Math.floor(h)}:${String(Math.round((h % 1) * 60)).padStart(2, '0')}`
}
</script>

<template>
  <div class="ph">
    <div><h1>{{ t('nav.staff') }}</h1><p>{{ t('staff.subtitle') }}</p></div>
    <span class="sp" />
    <UiButton v-if="auth.can('staff.create') && tab === 'list'" variant="primary" icon="plus" @click="openNew">{{ t('staff.new') }}</UiButton>
  </div>
  <div class="toolbar">
    <UiTabs v-model="tab" :items="tabs" :label="t('nav.staff')" />
    <template v-if="tab === 'list'">
      <UiInput v-model="q" type="search" icon="search" :placeholder="t('staff.searchPh')" />
      <button type="button" class="tgl" :aria-pressed="archived" @click="archived = !archived"><UiIcon name="archive" :size="16" />{{ t('staff.showArchived') }}</button>
    </template>
    <div v-else class="period">
      <button type="button" class="btn sm tgl" :aria-label="t('common.prev')" @click="day = isoDate(addDays(new Date(`${day}T12:00:00`), -1))"><svg class="ico flip-ico" aria-hidden="true"><use href="#i-arrow" /></svg></button>
      <input v-model="day" type="date" class="inp day-inp" :max="isoDate(new Date())" :aria-label="t('staff.day')" />
      <button type="button" class="btn sm tgl" :aria-label="t('common.next')" :disabled="day >= isoDate(new Date())" @click="day = isoDate(addDays(new Date(`${day}T12:00:00`), 1))"><svg class="ico" aria-hidden="true"><use href="#i-arrow" /></svg></button>
    </div>
  </div>

  <UiCard v-if="tab === 'list'" flush>
    <div v-if="!page" class="card-pad"><UiSkeleton :lines="6" /></div>
    <UiEmptyState v-else-if="!page.items.length" icon="teachers" :title="q ? t('common.nothingFound') : t('staff.empty')" />
    <div v-else class="scroll-x">
      <table class="tbl" style="min-width: 760px">
        <thead><tr><th>{{ t('staff.name') }}</th><th>{{ t('staff.roles') }}</th><th>{{ t('staff.branches') }}</th><th>{{ t('staff.lastLogin') }}</th><th class="r"><span class="sr">{{ t('books.actions') }}</span></th></tr></thead>
        <tbody>
          <tr v-for="s in page.items" :key="s.id" :class="{ muted: !!s.archived_at || !s.is_active }">
            <td>
              <div class="who2"><UiAvatar :name="s.full_name" size="sm" /><div><b>{{ s.full_name }}</b><div class="muted" style="font-size: 12px">{{ s.position || '—' }}<template v-if="s.phone"> · {{ formatPhone(s.phone) }}</template></div></div></div>
            </td>
            <td><div class="chips-row"><span v-for="r in s.roles" :key="r.id" class="chip">{{ te(`roles.${r.code}`) ? t(`roles.${r.code}`) : r.name }}</span></div></td>
            <td style="font-size: 13px">{{ s.branch_ids.map((b) => refs.branchName(b)).join(', ') || '—' }}</td>
            <td style="font-size: 13px">
              <span v-if="s.last_login_at">{{ relativeTime(s.last_login_at, loc) }}</span><span v-else class="muted">{{ t('staff.never') }}</span>
              <div><UiChip :tone="s.totp_enabled ? 'ok' : 'warn'" small>{{ s.totp_enabled ? t('user.twoFaOn') : t('user.twoFaOff') }}</UiChip><UiChip v-if="s.archived_at" small>{{ t('staff.archivedChip') }}</UiChip></div>
            </td>
            <td class="r">
              <div v-if="!s.archived_at" class="row-acts nowrap">
                <UiButton v-if="auth.can('staff.edit')" size="sm" variant="ghost" icon="edit" :title="t('common.edit')" :aria-label="`${t('common.edit')}: ${s.full_name}`" @click="edit(s)" />
                <UiButton v-if="auth.can('staff.edit')" size="sm" variant="ghost" icon="key" :title="t('staff.setPassword')" :aria-label="`${t('staff.setPassword')}: ${s.full_name}`" @click="pwFor = s; pw = ''; pwErr = null" />
                <UiButton v-if="isOwner && auth.can('security.manage') && s.totp_enabled && s.id !== auth.user?.id" size="sm" variant="ghost" icon="shield" :title="t('staff.reset2fa')" :aria-label="`${t('staff.reset2fa')}: ${s.full_name}`" @click="confirmFor = { s, kind: 'reset2fa' }" />
                <UiButton v-if="auth.can('staff.archive') && s.id !== auth.user?.id" size="sm" variant="ghost" icon="archive" :title="t('staff.archive')" :aria-label="`${t('staff.archive')}: ${s.full_name}`" @click="confirmFor = { s, kind: 'archive' }" />
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="page && page.total > LIMIT" class="card-pad"><UiPager v-model="offset" :total="page.total" :limit="LIMIT" /></div>
  </UiCard>

  <UiCard v-else-if="tab === 'checkins'" :title="t('staff.checkinsOf', { day: dayLabelText })">
    <UiSkeleton v-if="!checkins" :lines="5" />
    <UiEmptyState v-else-if="!checkins.length" icon="clock" :title="t('staff.noCheckins')" />
    <div v-for="r in checkins ?? []" :key="`${r.user_id}-${r.in_at}`" class="list-row">
      <UiAvatar :name="r.full_name" size="sm" />
      <div class="grow"><b>{{ r.full_name }}</b><span>{{ refs.branchName(r.branch_id) }}</span></div>
      <span class="num" style="font-size: 13px">{{ hm(r.in_at, loc) }} — {{ r.out_at ? hm(r.out_at, loc) : t('staff.stillIn') }}</span>
      <UiChip :tone="r.out_at ? undefined : 'ok'" small>{{ hours(r) }}</UiChip>
    </div>
  </UiCard>

  <UiCard v-else :title="t('staff.reportsOf', { day: dayLabelText })">
    <UiSkeleton v-if="!reports" :lines="5" />
    <UiEmptyState v-else-if="!reports.length" icon="note" :title="t('staff.noReports')" />
    <div v-else class="fb-list">
      <article v-for="r in reports" :key="r.user_id" class="fb-item">
        <header><b>{{ r.full_name }}</b><span class="fb-meta">{{ hm(r.updated_at, loc) }}</span></header>
        <p class="m0 pre">{{ r.text }}</p>
      </article>
    </div>
  </UiCard>

  <StaffDrawer v-model:open="drawer" :staff="editing" :roles="roles" @saved="loadStaff" />
  <UiModal :open="!!pwFor" :title="t('staff.setPasswordFor', { name: pwFor?.full_name ?? '' })" @update:open="(v) => !v && (pwFor = null)">
    <form id="pw-form" class="stack" @submit.prevent="setPassword">
      <UiInput v-model="pw" type="password" :label="t('staff.newPassword')" :hint="t('staff.passwordHint')" autocomplete="new-password" autofocus />
      <p class="form-note">{{ t('staff.passwordNote') }}</p>
      <p v-if="pwErr" class="form-err" role="alert">{{ pwErr }}</p>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton type="submit" form="pw-form" variant="primary" :loading="busy" :disabled="pw.length < 8">{{ t('staff.setPassword') }}</UiButton>
    </template>
  </UiModal>
  <UiPrompt
    :open="!!confirmFor"
    :title="confirmFor?.kind === 'archive' ? t('staff.archiveTitle') : t('staff.reset2faTitle')"
    :text="confirmFor ? t(confirmFor.kind === 'archive' ? 'staff.archiveText' : 'staff.reset2faText', { name: confirmFor.s.full_name }) : ''"
    :confirm-label="confirmFor?.kind === 'archive' ? t('staff.archive') : t('staff.reset2fa')"
    danger
    :busy="busy"
    @update:open="(v) => !v && (confirmFor = null)"
    @confirm="confirmAction"
  />
</template>
