<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { UiButton, UiCard, UiChip, UiDrawer, UiEmptyState, UiIcon, UiSegmented, UiSkeleton, UiTextarea } from '@/components/ui'
import { complaintsApi, type Complaint, type ComplaintStatus } from '@/api/compliance'
import { COMPLAINT_TONE, complaintActions } from '@/components/compliance/complaintMeta'
import { useAuthStore } from '@/stores/auth'
import { useBranchStore } from '@/stores/branch'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import { dmy, hm } from '@/utils/dates'
import { relativeTime } from '@/utils/format'
import { apiErr } from '@/utils/err'
import { safeUrl } from '@/utils/url'
import type { Locale } from '@/i18n'

/** Handler queue: acknowledge within 24 h, answer within 3 business days (7 when a check is needed). */
const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const branch = useBranchStore()
const refs = useRefsStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)

const items = ref<Complaint[] | null>(null)
const filter = ref<'open' | ComplaintStatus | ''>('open')
const answer = ref('')
const acting = ref<string | null>(null)
const error = ref<string | null>(null)

const OPEN: ComplaintStatus[] = ['new', 'acknowledged', 'investigating', 'appealed']
const filters = computed(() => (['open', 'answered', 'closed', ''] as const).map((v) => ({ value: v, label: t(`complaints.filter.${v || 'all'}`) })))
const shown = computed(() => (items.value ?? [])
  .filter((c) => branch.filterId === null || c.branch_id === branch.filterId)
  .filter((c) => (filter.value === 'open' ? OPEN.includes(c.status) : !filter.value || c.status === filter.value)))
const overdueCount = computed(() => (items.value ?? []).filter((c) => c.overdue).length)
const openId = computed(() => (route.params.id ? Number(route.params.id) : null))
const current = computed(() => items.value?.find((c) => c.id === openId.value) ?? null)
const drawer = computed({ get: () => openId.value !== null, set: (v) => !v && router.replace('/complaints') })
const actions = computed(() => (current.value && auth.can('complaints.answer') ? complaintActions(current.value.status, !!auth.user?.roles.includes('owner')) : []))
const name = (id: number | null | undefined) => (id ? refs.staffById.get(id)?.full_name ?? t('complaints.userN', { n: id }) : '')

async function load() {
  items.value = await complaintsApi.list().catch(() => [])
}
onMounted(() => {
  refs.load()
  refs.loadStaff()
  load()
})
watch(openId, () => {
  answer.value = current.value?.answer ?? ''
  error.value = null
})

async function act(a: 'acknowledge' | 'investigate' | 'answer' | 'close') {
  const c = current.value
  if (!c) return
  if (a === 'answer' && answer.value.trim().length < 5) {
    error.value = t('complaints.answerRequired')
    return
  }
  acting.value = a
  error.value = null
  try {
    const next = await complaintsApi.act(c.id, a, a === 'answer' ? answer.value.trim() : undefined)
    items.value = items.value?.map((x) => (x.id === c.id ? { ...x, ...next, overdue: OPEN.includes(next.status) && new Date(next.due_at) < new Date() } : x)) ?? null
    toast.ok(t(`complaints.done.${a}`))
  } catch (e) {
    error.value = apiErr(e) ?? t('errors.generic')
  } finally {
    acting.value = null
  }
}
const dueText = (c: Complaint) => (c.overdue ? t('complaints.overdue', { when: relativeTime(c.due_at, loc.value) }) : t('complaints.dueAt', { date: `${dmy(c.due_at, loc.value)} ${hm(c.due_at, loc.value)}` }))
</script>

<template>
  <div class="ph">
    <div><h1>{{ t('nav.complaints') }}</h1><p>{{ t('complaints.subtitle') }}</p></div>
    <span class="sp" />
    <UiButton to="/feedback" icon="plus">{{ t('complaints.fileOwn') }}</UiButton>
  </div>
  <div class="toolbar">
    <UiSegmented v-model="filter" :options="filters" :label="t('complaints.filterLabel')" size="sm" />
    <UiChip v-if="overdueCount" tone="red" icon="alert">{{ t('complaints.overdueN', { n: overdueCount }) }}</UiChip>
  </div>

  <UiCard flush>
    <div v-if="!items" class="card-pad"><UiSkeleton :lines="5" /></div>
    <UiEmptyState v-else-if="!shown.length" icon="flag" :title="filter === 'open' ? t('complaints.noOpen') : t('complaints.empty')" />
    <div v-else class="card-b">
      <RouterLink v-for="c in shown" :key="c.id" :to="`/complaints/${c.id}`" class="list-row task-row" :class="{ overdue: c.overdue, done: c.status === 'closed' }">
        <UiIcon name="flag" :size="18" :class="c.overdue ? 'redc' : 'muted'" />
        <div class="grow">
          <b>{{ c.subject }}</b>
          <span>{{ refs.branchName(c.branch_id) || t('complaints.noBranch') }} · {{ relativeTime(c.created_at, loc) }}<template v-if="c.against_user_id"> · {{ t('complaints.about', { name: name(c.against_user_id) }) }}</template></span>
        </div>
        <div class="task-side">
          <UiChip :tone="COMPLAINT_TONE[c.status]" small>{{ t(`complaints.status.${c.status}`) }}</UiChip>
          <span v-if="OPEN.includes(c.status)" class="due num" :class="{ redc: c.overdue }"><UiIcon v-if="c.overdue" name="alert" :size="14" />{{ dueText(c) }}</span>
        </div>
      </RouterLink>
    </div>
  </UiCard>

  <UiDrawer v-model:open="drawer" :title="current?.subject ?? t('nav.complaints')">
    <UiEmptyState v-if="items && !current" icon="flag" :title="t('complaints.notFound')" />
    <div v-else-if="current" class="stack">
      <div class="chips-row">
        <UiChip :tone="COMPLAINT_TONE[current.status]">{{ t(`complaints.status.${current.status}`) }}</UiChip>
        <UiChip v-if="current.overdue" tone="red" icon="alert">{{ dueText(current) }}</UiChip>
        <span v-else-if="OPEN.includes(current.status)" class="chip">{{ dueText(current) }}</span>
      </div>
      <dl class="dl">
        <dt>{{ t('complaints.from') }}</dt><dd>{{ name(current.author_id) }}</dd>
        <template v-if="current.against_user_id"><dt>{{ t('complaints.against') }}</dt><dd>{{ name(current.against_user_id) }}</dd></template>
        <dt>{{ t('branch.label') }}</dt><dd>{{ refs.branchName(current.branch_id) || '—' }}</dd>
        <dt>{{ t('complaints.created') }}</dt><dd>{{ dmy(current.created_at, loc) }} {{ hm(current.created_at, loc) }}</dd>
        <template v-if="current.acknowledged_at"><dt>{{ t('complaints.acknowledged') }}</dt><dd>{{ dmy(current.acknowledged_at, loc) }} {{ hm(current.acknowledged_at, loc) }}</dd></template>
      </dl>
      <div class="fb-answer"><p class="m0 pre">{{ current.body }}</p></div>
      <a v-if="safeUrl(current.file_url)" :href="safeUrl(current.file_url)!" target="_blank" rel="noopener" class="rowlink"><UiIcon name="clip" :size="14" /> {{ t('complaints.file') }}</a>
      <p v-if="current.status === 'appealed' && !auth.user?.roles.includes('owner')" class="alert info m0"><span>{{ t('complaints.appealOwner') }}</span></p>
      <template v-if="actions.includes('answer')">
        <UiTextarea v-model="answer" :label="t('complaints.answerLabel')" :placeholder="t('complaints.answerPh')" :rows="5" :maxlength="8000" />
      </template>
      <div v-else-if="current.answer">
        <span class="fb-meta">{{ t('feedback.answer') }}<template v-if="current.answered_at"> · {{ dmy(current.answered_at, loc) }}</template></span>
        <div class="fb-answer"><p class="m0 pre">{{ current.answer }}</p></div>
      </div>
      <p v-if="error" class="form-err" role="alert">{{ error }}</p>
      <div v-if="actions.length" class="row-acts" style="justify-content: flex-start">
        <UiButton v-for="a in actions" :key="a" :variant="a === 'answer' ? 'primary' : a === 'close' ? 'ghost' : 'navy'" :loading="acting === a" @click="act(a)">{{ t(`complaints.do.${a}`) }}</UiButton>
      </div>
    </div>
    <UiSkeleton v-else :lines="5" />
  </UiDrawer>
</template>
