<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiCard, UiChip, UiEmptyState, UiField, UiInput, UiPrompt, UiSelect, UiSkeleton, UiTextarea } from '@/components/ui'
import { complaintsApi, type Complaint } from '@/api/compliance'
import { portalApi } from '@/api/portal'
import { useAuthStore } from '@/stores/auth'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import { dmy } from '@/utils/dates'
import { apiErr } from '@/utils/err'
import { COMPLAINT_TONE } from '@/components/compliance/complaintMeta'
import type { Locale } from '@/i18n'

/** «Жалобы и предложения» for every user: file one, follow the answer, appeal it to the operations director. */
const { t, locale } = useI18n()
const auth = useAuthStore()
const refs = useRefsStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)
const items = ref<Complaint[] | null>(null)
const form = reactive({ subject: '', body: '', against: 0 })
const people = ref<{ value: number; label: string }[]>([])
const error = ref<string | null>(null)
const busy = ref(false)
const appealing = ref<Complaint | null>(null)
const appealBusy = ref(false)

const againstOptions = computed(() => [{ value: 0, label: t('feedback.nobody') }, ...people.value])

onMounted(async () => {
  items.value = await complaintsApi.my().catch(() => [])
  if (auth.isStaff) {
    await refs.loadStaff()
    people.value = refs.staff.filter((s) => s.id !== auth.user?.id).map((s) => ({ value: s.id, label: s.position ? `${s.full_name} · ${s.position}` : s.full_name }))
  } else {
    const me = await portalApi.me().catch(() => null)
    const seen = new Map<number, string>()
    for (const c of me?.children ?? []) for (const g of c.groups) if (g.teacher_id && g.teacher) seen.set(g.teacher_id, g.teacher)
    people.value = [...seen].map(([id, name]) => ({ value: id, label: t('feedback.teacherOf', { name }) }))
  }
})

async function submit() {
  error.value = form.subject.trim().length < 3 ? t('feedback.subjectRequired') : form.body.trim().length < 10 ? t('feedback.bodyRequired') : null
  if (error.value) return
  busy.value = true
  try {
    const c = await complaintsApi.create({ subject: form.subject.trim(), body: form.body.trim(), against_user_id: form.against || null })
    items.value = [c, ...(items.value ?? [])]
    Object.assign(form, { subject: '', body: '', against: 0 })
    toast.ok(t('feedback.sent', { date: dmy(c.due_at, loc.value) }))
  } catch (e) {
    error.value = apiErr(e) ?? t('errors.generic')
  } finally {
    busy.value = false
  }
}

async function appeal() {
  const c = appealing.value
  if (!c) return
  appealBusy.value = true
  try {
    const next = await complaintsApi.act(c.id, 'appeal')
    items.value = items.value?.map((x) => (x.id === c.id ? next : x)) ?? null
    toast.ok(t('feedback.appealed'))
    appealing.value = null
  } catch (e) {
    toast.error(apiErr(e) ?? t('errors.generic'))
  } finally {
    appealBusy.value = false
  }
}
</script>

<template>
  <div class="ph"><div><h1>{{ t('nav.feedback') }}</h1><p>{{ t('feedback.subtitle') }}</p></div></div>

  <div class="grid fin-a">
    <UiCard :title="t('feedback.history')">
      <UiSkeleton v-if="!items" :lines="4" />
      <UiEmptyState v-else-if="!items.length" icon="flag" :title="t('feedback.empty')" :text="t('feedback.emptyText')" />
      <div v-else class="fb-list">
        <article v-for="c in items" :key="c.id" class="fb-item">
          <header>
            <b>{{ c.subject }}</b>
            <UiChip :tone="COMPLAINT_TONE[c.status]" small>{{ t(`complaints.status.${c.status}`) }}</UiChip>
          </header>
          <p class="m0 pre muted">{{ c.body }}</p>
          <span class="fb-meta">{{ t('feedback.sentAt', { date: dmy(c.created_at, loc) }) }}<template v-if="c.status !== 'answered' && c.status !== 'closed'"> · {{ t('feedback.dueAt', { date: dmy(c.due_at, loc) }) }}</template></span>
          <div v-if="c.answer" class="fb-answer">
            <span class="fb-meta">{{ t('feedback.answer') }}<template v-if="c.answered_at"> · {{ dmy(c.answered_at, loc) }}</template></span>
            <p class="m0 pre">{{ c.answer }}</p>
          </div>
          <div v-if="c.status === 'answered'" class="row-acts" style="justify-content: flex-start">
            <UiButton size="sm" variant="ghost" icon="flag" @click="appealing = c">{{ t('feedback.appeal') }}</UiButton>
          </div>
        </article>
      </div>
    </UiCard>

    <UiCard :title="t('feedback.new')">
      <form class="stack" @submit.prevent="submit">
        <UiInput v-model="form.subject" :label="t('feedback.subject')" :placeholder="t('feedback.subjectPh')" :maxlength="255" />
        <UiTextarea v-model="form.body" :label="t('feedback.body')" :placeholder="t('feedback.bodyPh')" :rows="5" :maxlength="8000" />
        <UiField v-if="people.length" :label="t('feedback.against')" :hint="t('feedback.againstHint')"><UiSelect v-model="form.against" :options="againstOptions" :label="t('feedback.against')" block /></UiField>
        <p class="form-note">{{ t('feedback.note') }}</p>
        <p v-if="error" class="form-err" role="alert">{{ error }}</p>
        <div><UiButton type="submit" variant="primary" icon="send" :loading="busy">{{ t('feedback.send') }}</UiButton></div>
      </form>
    </UiCard>
  </div>

  <UiPrompt :open="!!appealing" :title="t('feedback.appealTitle')" :text="t('feedback.appealText')" :confirm-label="t('feedback.appeal')" :busy="appealBusy" @update:open="(v) => !v && (appealing = null)" @confirm="appeal" />
</template>
