<script setup lang="ts">
import { useSourceLabel } from '@/composables/useSourceLabel'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { UiAvatar, UiButton, UiCard, UiChip, UiEmptyState, UiIcon, UiPrompt, UiSkeleton, UiTable, UiTabs, type TableColumn } from '@/components/ui'
import StatusChip from '@/components/students/StatusChip.vue'
import LevelTag from '@/components/students/LevelTag.vue'
import PaymentModal from '@/components/students/PaymentModal.vue'
import TransferModal from '@/components/students/TransferModal.vue'
import FreezeModal from '@/components/students/FreezeModal.vue'
import GuardianModal from '@/components/students/GuardianModal.vue'
import RefundModal from '@/components/students/RefundModal.vue'
import StudentEditModal from '@/components/students/StudentEditModal.vue'
import AttendanceCard from '@/components/students/AttendanceCard.vue'
import StudentCoinsTab from '@/components/store/StudentCoinsTab.vue'
import StudentBooksTab from '@/components/store/StudentBooksTab.vue'
import { studentsApi, type Attempt, type AttendanceMark, type LedgerEntry, type Student } from '@/api/students'
import { paymentsApi, type Payment } from '@/api/payments'
import { chatsApi } from '@/api/chats'
import { ApiError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import { dmy, money } from '@/utils/dates'
import { shortDate } from '@/utils/format'
import { formatPhone } from '@/utils/phone'
import type { Locale } from '@/i18n'

type Tab = 'overview' | 'ledger' | 'payments' | 'tests' | 'coins' | 'books'

const { t, locale } = useI18n()
const srcLabel = useSourceLabel()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const refs = useRefsStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)

const s = ref<Student | null>(null)
const notFound = ref(false)
const tab = ref<Tab>('overview')
const ledger = ref<LedgerEntry[] | null>(null)
const payments = ref<Payment[] | null>(null)
const attempts = ref<Attempt[] | null>(null)
const marks = ref<AttendanceMark[] | null>(null)
const modal = ref<'pay' | 'transfer' | 'freeze' | 'guardian' | 'unfreeze' | 'archive' | 'edit' | null>(null)
const refundOf = ref<Payment | null>(null)
const busy = ref(false)

const id = computed(() => Number(route.params.id))
const activeGroups = computed(() => s.value?.groups.filter((g) => !g.left_on) ?? [])
const left = computed(() => s.value?.balance.lessons_left ?? 0)
const ringTone = computed(() => (left.value <= 0 ? 'var(--red)' : left.value <= 3 ? 'var(--warn)' : 'var(--ok)'))
const ringDash = computed(() => {
  const c = 2 * Math.PI * 40
  return `${(Math.min(1, Math.max(0, left.value) / 12) * c).toFixed(1)} ${c.toFixed(1)}`
})

const tabs = computed(() => {
  const items: { value: Tab; label: string }[] = [{ value: 'overview', label: t('students.tab.overview') }]
  items.push({ value: 'ledger', label: t('students.tab.ledger') })
  if (auth.can('payments.view')) items.push({ value: 'payments', label: t('students.tab.payments') })
  items.push({ value: 'tests', label: t('students.tab.tests') })
  if (auth.can('coins.view')) items.push({ value: 'coins', label: t('students.tab.coins') })
  items.push({ value: 'books', label: t('students.tab.books') })
  return items
})

async function load() {
  notFound.value = false
  try {
    s.value = await studentsApi.get(id.value)
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 403)) notFound.value = true
    return
  }
  ledger.value = payments.value = attempts.value = marks.value = null
  if (auth.can('payments.view')) loadPayments()
  studentsApi.attendance(id.value).then((m) => (marks.value = m), () => (marks.value = []))
  if (tab.value !== 'overview') loadTab(tab.value)
}

async function loadPayments() {
  payments.value = (await paymentsApi.list({ student_id: id.value, limit: 50 }).catch(() => ({ items: [] }))).items
}

async function loadTab(v: Tab) {
  if (v === 'ledger' && !ledger.value) ledger.value = await studentsApi.ledger(id.value).catch(() => [])
  if (v === 'tests' && !attempts.value) {
    attempts.value = await studentsApi.tests(id.value).catch(() => [])
  }
}

watch(id, load, { immediate: true })
watch(tab, loadTab)

function updated(next: Student) {
  s.value = next
  ledger.value = null
  if (tab.value === 'ledger') loadTab('ledger')
}

async function afterPayment() {
  await load()
}

async function message() {
  if (!s.value?.user_id) return
  try {
    const chat = await chatsApi.direct(s.value.user_id)
    router.push({ path: `/chats/${chat.id}` })
  } catch {
    /* the 403 reason is shown as a toast */
  }
}

async function unfreeze() {
  if (!s.value) return
  busy.value = true
  try {
    updated(await studentsApi.unfreeze(s.value.id))
    toast.ok(t('students.unfrozen'))
    modal.value = null
  } finally {
    busy.value = false
  }
}

async function archive() {
  if (!s.value) return
  busy.value = true
  try {
    await studentsApi.archive(s.value.id)
    toast.ok(t('students.archived'))
    router.push('/students')
  } finally {
    busy.value = false
  }
}

const ledgerCols = computed<TableColumn[]>(() => [
  { key: 'at', label: t('students.col.date') },
  { key: 'kind', label: t('students.ledger.kind') },
  { key: 'lessons_delta', label: t('students.ledger.lessons'), align: 'right' },
  { key: 'money_delta', label: t('students.ledger.money'), align: 'right' },
  { key: 'lessons_after', label: t('students.ledger.after'), align: 'right' },
])
const payCols = computed<TableColumn[]>(() => [
  { key: 'paid_at', label: t('students.col.date') },
  { key: 'amount', label: t('payments.col.amount'), align: 'right' },
  { key: 'method', label: t('payments.col.method') },
  { key: 'actions', label: '', align: 'right' },
])
const signed = (n: number) => (n > 0 ? `+${n}` : String(n))
const kindLabel = (k: string) => (['payment', 'lesson', 'transfer', 'refund', 'freeze', 'manual', 'trial'].includes(k) ? t(`students.ledger.k.${k}`) : k)
const recentPayments = computed(() => payments.value?.slice(0, 4) ?? [])
const canRefund = (p: Payment) => auth.can('payments.refund') && p.refunded < p.amount
</script>

<template>
  <UiEmptyState v-if="notFound" large icon="users" :title="t('students.notFound')" :text="t('notFound.text')">
    <UiButton to="/students" icon="arrow">{{ t('students.title') }}</UiButton>
  </UiEmptyState>

  <template v-else-if="!s">
    <div class="card" style="padding: 20px; margin-bottom: 16px"><UiSkeleton :lines="3" /></div>
    <div class="grid stu-grid"><div v-for="i in 3" :key="i" class="card" style="padding: 18px"><UiSkeleton :lines="4" /></div></div>
  </template>

  <template v-else>
    <nav class="crumbs" :aria-label="t('common.breadcrumbs')">
      <RouterLink to="/students">{{ t('students.title') }}</RouterLink>
      <template v-if="activeGroups[0]"> / <RouterLink v-if="auth.can('schedule.view')" :to="`/groups/${activeGroups[0].id}`">{{ activeGroups[0].name }}</RouterLink><span v-else>{{ activeGroups[0].name }}</span></template>
      / <span>{{ s.full_name }}</span>
    </nav>

    <div class="card" style="margin-bottom: 16px">
      <div class="stu-head">
        <UiAvatar :name="s.full_name" :src="s.photo_url" size="lg" />
        <div style="flex: 1; min-width: 220px">
          <h2>{{ s.full_name }}</h2>
          <div class="muted" style="margin-top: 2px">
            <template v-if="s.age !== null">{{ t('students.age', { n: s.age }) }} · </template>
            <template v-if="s.phone">{{ formatPhone(s.phone) }} · </template>
            {{ t('students.since', { date: shortDate(s.created_at, loc) }) }}
          </div>
          <div class="facts">
            <StatusChip :status="s.status" />
            <span v-if="s.level_id" class="chip"><LevelTag :id="s.level_id" full /></span>
            <span v-for="g in activeGroups" :key="g.id" class="chip">{{ t('students.groupN', { name: g.name }) }}</span>
            <span class="chip">{{ refs.branchName(s.branch_id) }}</span>
          </div>
        </div>
        <div class="head-acts">
          <UiButton v-if="auth.can('students.edit')" icon="edit" @click="modal = 'edit'">{{ t('students.edit.action') }}</UiButton>
          <UiButton v-if="auth.can('chats.use') && s.user_id" icon="chat" @click="message">{{ t('students.message') }}</UiButton>
          <UiButton v-if="auth.can('students.transfer') && s.status !== 'frozen'" icon="arrow" @click="modal = 'transfer'">{{ t('students.transfer.action') }}</UiButton>
          <UiButton v-if="auth.can('students.transfer') && s.status === 'active'" icon="clock" @click="modal = 'freeze'">{{ t('students.freeze.action') }}</UiButton>
          <UiButton v-if="auth.can('students.transfer') && s.status === 'frozen'" icon="play" @click="modal = 'unfreeze'">{{ t('students.unfreeze') }}</UiButton>
          <UiButton v-if="auth.can('payments.create')" variant="primary" icon="wallet" @click="modal = 'pay'">{{ t('payments.take') }}</UiButton>
        </div>
      </div>
      <UiTabs v-model="tab" :items="tabs" :label="t('students.title')" class="stu-tabs" />
    </div>

    <Transition name="fade" mode="out-in">
      <div v-if="tab === 'overview'" key="o">
        <div v-if="left <= 3 && s.status === 'active'" class="alert" :class="{ red: left <= 0 }">
          <UiIcon name="alert" :size="24" />
          <div class="grow">
            <b>{{ left <= 0 ? t('students.alert.debt', { n: -left }) : t('students.alert.few', { n: left }) }}</b>
            <span>{{ t('students.alert.text') }}</span>
          </div>
          <UiButton v-if="auth.can('payments.create')" size="sm" variant="primary" @click="modal = 'pay'">{{ t('students.alert.extend') }}</UiButton>
        </div>

        <div class="grid stu-grid stagger">
          <UiCard :title="t('students.balance')">
            <div class="balance">
              <svg class="ring" viewBox="0 0 96 96" role="img" :aria-label="t('students.lessonsLeft', { n: left })">
                <circle cx="48" cy="48" r="40" fill="none" stroke="var(--grid)" stroke-width="10" />
                <circle cx="48" cy="48" r="40" fill="none" :stroke="ringTone" stroke-width="10" stroke-linecap="round" :stroke-dasharray="ringDash" transform="rotate(-90 48 48)" class="ring-arc" />
                <text x="48" y="52" text-anchor="middle" font-size="22" fill="var(--ink)">{{ left }}</text>
                <text x="48" y="67" text-anchor="middle" font-size="9" fill="var(--muted)" style="font-family: 'Golos Text'; font-weight: 500">{{ t('students.ringSub') }}</text>
              </svg>
              <dl class="bal-l">
                <dt>{{ t('students.bal.paid') }}</dt><dd>{{ s.balance.lessons_paid }}</dd>
                <dt>{{ t('students.bal.done') }}</dt><dd>{{ s.balance.lessons_done }}</dd>
                <dt>{{ t('students.bal.left') }}</dt><dd :style="{ color: ringTone }">{{ left }}</dd>
                <dt>{{ t('students.bal.price') }}</dt><dd>{{ money(s.balance.lesson_price, loc) }}</dd>
                <dt>{{ t('students.bal.money') }}</dt><dd>{{ money(s.balance.money_balance, loc) }}</dd>
              </dl>
            </div>
          </UiCard>

          <UiCard :title="t('students.groups')">
            <div v-if="activeGroups.length" class="lr-list">
              <component :is="auth.can('schedule.view') ? 'RouterLink' : 'div'" v-for="g in activeGroups" :key="g.id" :to="`/groups/${g.id}`" class="list-row">
                <span class="av" :style="{ borderRadius: '10px' }">{{ g.name.slice(0, 2) }}</span>
                <div class="grow"><b>{{ g.name }}</b><span>{{ refs.level(g.level_id)?.name }} · {{ t('students.joined', { date: dmy(g.joined_on, loc) }) }}</span></div>
              </component>
            </div>
            <p v-else class="muted m0">{{ t('students.noGroups') }}</p>
            <div v-if="s.stars || s.coins" class="coins" style="margin-top: 12px">
              <span class="coin sm">OE</span>
              <div><b class="num">{{ s.coins }}</b> <span class="muted">{{ t('students.coins') }}</span> · <b class="num">{{ s.stars }}</b> <span class="muted">{{ t('students.stars') }}</span></div>
            </div>
          </UiCard>

          <AttendanceCard :marks="marks" />

          <UiCard :title="t('students.guardians')">
            <template v-if="auth.can('students.edit')" #actions>
              <UiButton size="sm" variant="ghost" icon="plus" @click="modal = 'guardian'">{{ t('common.add') }}</UiButton>
            </template>
            <div v-for="g in s.guardians" :key="g.id" class="list-row">
              <UiAvatar :name="g.full_name" />
              <div class="grow"><b>{{ g.full_name }}<template v-if="g.relation"> · {{ g.relation }}</template></b><span>{{ g.phone ? formatPhone(g.phone) : '—' }}</span></div>
              <span v-if="g.notify" class="srcico wa" :title="t('students.notifyOn')"><svg><use href="#i-wa" /></svg></span>
            </div>
            <p v-if="!s.guardians.length" class="muted m0">{{ t('students.noGuardians') }}</p>
          </UiCard>

          <UiCard v-if="auth.can('payments.view')" :title="t('students.tab.payments')">
            <template #actions><span v-if="s.source" class="muted" style="font-size: 12px">{{ t('students.sourceIs', { src: srcLabel(s.source) }) }}</span></template>
            <UiSkeleton v-if="!payments" :lines="3" />
            <table v-else-if="recentPayments.length">
              <tbody>
                <tr v-for="p in recentPayments" :key="p.id">
                  <td class="num">{{ dmy(p.paid_at, loc) }}</td>
                  <td class="r num">{{ money(p.amount, loc) }}<div class="muted" style="font-size: 12px">{{ t('students.nLessons', { n: p.lessons }) }}</div></td>
                  <td><span class="method"><i :class="p.method === 'kaspi' && 'kaspi'" :style="p.method !== 'kaspi' ? { background: `var(--${p.method === 'cash' ? 'ok' : 'info'})` } : undefined">{{ p.method === 'kaspi' ? 'K' : p.method === 'cash' ? '₸' : '▭' }}</i>{{ t(`payments.method.${p.method}`) }}</span></td>
                </tr>
              </tbody>
            </table>
            <p v-else class="muted m0">{{ t('students.noPayments') }}</p>
          </UiCard>

          <UiCard v-if="s.notes" :title="t('students.form.notes')"><p class="m0 pre">{{ s.notes }}</p></UiCard>
        </div>
        <div v-if="auth.can('students.archive') && !s.archived_at" class="danger-zone">
          <UiButton size="sm" variant="ghost" danger icon="archive" @click="modal = 'archive'">{{ t('students.archive') }}</UiButton>
        </div>
      </div>

      <UiCard v-else-if="tab === 'ledger'" key="l" flush>
        <UiTable :columns="ledgerCols" :rows="ledger ?? []" :loading="!ledger">
          <template #cell-at="{ row }"><span class="num">{{ dmy(row.at as string, loc) }}</span></template>
          <template #cell-kind="{ row }"><b>{{ kindLabel(row.kind as string) }}</b><div v-if="row.note" class="muted" style="font-size: 12px">{{ row.note }}</div></template>
          <template #cell-lessons_delta="{ row }"><span class="num" :class="{ okc: (row.lessons_delta as number) > 0 }">{{ signed(row.lessons_delta as number) }}</span></template>
          <template #cell-money_delta="{ row }"><span class="num">{{ (row.money_delta as number) ? money(row.money_delta as number, loc) : '—' }}</span></template>
          <template #cell-lessons_after="{ row }"><b class="num">{{ row.lessons_after }}</b></template>
          <template #empty><UiEmptyState icon="history" :title="t('students.ledger.empty')" /></template>
        </UiTable>
      </UiCard>

      <UiCard v-else-if="tab === 'payments'" key="p" flush>
        <UiTable :columns="payCols" :rows="payments ?? []" :loading="!payments">
          <template #cell-paid_at="{ row }"><span class="num">{{ dmy(row.paid_at as string, loc) }}</span></template>
          <template #cell-amount="{ row }">
            <b class="num">{{ money(row.amount as number, loc) }}</b>
            <div class="muted" style="font-size: 12px">{{ t('students.nLessons', { n: row.lessons }) }}<template v-if="(row.refunded as number) > 0"> · <span class="redc">{{ t('payments.refunded', { sum: money(row.refunded as number, loc) }) }}</span></template></div>
          </template>
          <template #cell-method="{ row }">{{ t(`payments.method.${row.method}`) }}</template>
          <template #cell-actions="{ row }">
            <UiButton v-if="canRefund(row)" size="sm" variant="ghost" icon="history" @click="refundOf = row">{{ t('payments.refund') }}</UiButton>
          </template>
          <template #empty><UiEmptyState icon="wallet" :title="t('students.noPayments')" /></template>
        </UiTable>
      </UiCard>

      <StudentCoinsTab v-else-if="tab === 'coins'" key="c" :student="s" />
      <StudentBooksTab v-else-if="tab === 'books'" key="b" :student="s" @sold="afterPayment" />
      <UiCard v-else key="t" flush>
        <div v-if="!attempts" style="padding: 18px"><UiSkeleton :lines="3" /></div>
        <div v-else-if="attempts.length" class="card-b" style="padding-top: 6px">
          <div v-for="a in attempts" :key="a.id" class="list-row">
            <span class="grade">{{ a.score }}</span>
            <div class="grow">
              <b>{{ a.test_title ?? t('students.testN', { n: a.test_id }) }}</b>
              <span>{{ t('students.score', { s: a.score, max: a.max_score ?? '—' }) }}<template v-if="a.finished_at"> · {{ shortDate(a.finished_at, loc) }}</template><template v-if="a.recommended_level_id"> · {{ t('students.recommended', { lv: refs.level(a.recommended_level_id)?.name }) }}</template></span>
            </div>
            <UiChip :tone="a.status === 'reviewed' || a.status === 'done' ? 'ok' : 'warn'" small>{{ t(`students.attempt.${a.status}`, a.status) }}</UiChip>
          </div>
        </div>
        <UiEmptyState v-else icon="tests" :title="t('students.noTests')" />
      </UiCard>
    </Transition>

    <PaymentModal :open="modal === 'pay'" :student="s" @update:open="(v) => !v && (modal = null)" @paid="afterPayment" />
    <TransferModal :open="modal === 'transfer'" :student="s" @update:open="(v) => !v && (modal = null)" @done="updated" />
    <FreezeModal :open="modal === 'freeze'" :student="s" @update:open="(v) => !v && (modal = null)" @done="updated" />
    <StudentEditModal :open="modal === 'edit'" :student="s" @update:open="(v) => !v && (modal = null)" @done="updated" />
    <GuardianModal :open="modal === 'guardian'" :student="s" @update:open="(v) => !v && (modal = null)" @done="updated" />
    <RefundModal :payment="refundOf" @close="refundOf = null" @done="afterPayment" />
    <UiPrompt :open="modal === 'unfreeze'" :title="t('students.unfreeze')" :text="t('students.unfreezeText')" :confirm-label="t('students.unfreeze')" :busy="busy" @update:open="(v) => !v && (modal = null)" @confirm="unfreeze" />
    <UiPrompt :open="modal === 'archive'" :title="t('students.archive')" :text="t('students.archiveText', { name: s.full_name })" :confirm-label="t('students.archive')" danger :busy="busy" @update:open="(v) => !v && (modal = null)" @confirm="archive" />
  </template>
</template>
