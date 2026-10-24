<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiChip, UiEmptyState, UiIcon, UiSkeleton, UiTextarea } from '@/components/ui'
import { portalApi, type PortalHomework } from '@/api/portal'
import { chatsApi } from '@/api/chats'
import { usePortalStore } from '@/stores/portal'
import { useToastStore } from '@/stores/toast'
import { dayLabel, hm } from '@/utils/dates'
import { apiErr } from '@/utils/err'
import { safeUrl } from '@/utils/url'
import type { Locale } from '@/i18n'

/** Homework: everyone sees tasks and grades; only the student account submits (text and / or a file). */
const { t, locale } = useI18n()
const portal = usePortalStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)
const items = ref<PortalHomework[] | null>(null)
const openId = ref<number | null>(null)
const draft = reactive<{ answer: string; file: { key: string; name: string; url: string } | null }>({ answer: '', file: null })
const uploading = ref(false)
const busy = ref(false)
const error = ref<string | null>(null)
const canSubmit = computed(() => portal.me?.kind === 'student')

watch(() => portal.child?.id, async (id) => {
  items.value = null
  if (id) items.value = await portalApi.homework(id).catch(() => [])
}, { immediate: true })

const TONE: Record<string, 'ok' | 'warn' | 'info' | 'red' | undefined> = { assigned: 'warn', submitted: 'info', checked: 'ok' }
const statusLabel = (s: string) => (['assigned', 'submitted', 'checked'].includes(s) ? t(`portal.hw.${s}`) : s)
const overdue = (h: PortalHomework) => h.status === 'assigned' && !!h.due_at && new Date(h.due_at) < new Date()

function start(h: PortalHomework) {
  openId.value = h.id
  draft.answer = h.answer ?? ''
  draft.file = null
  error.value = null
}
async function pickFile(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (!f) return
  uploading.value = true
  error.value = null
  try {
    const r = await chatsApi.upload(f)
    draft.file = { key: r.key, name: r.name, url: r.url }
  } catch (err) {
    error.value = apiErr(err) ?? t('errors.generic')
  } finally {
    uploading.value = false
  }
}
async function submit(h: PortalHomework) {
  const id = portal.child?.id
  if (!id) return
  error.value = !draft.answer.trim() && !draft.file ? t('portal.hw.empty') : null
  if (error.value) return
  busy.value = true
  try {
    await portalApi.submit(h.id, { student_id: id, answer: draft.answer.trim() || null, file_key: draft.file?.key ?? null })
    h.status = 'submitted'
    h.answer = draft.answer.trim() || null
    if (draft.file) h.file_url = draft.file.url
    openId.value = null
    toast.ok(t('portal.hw.sent'))
  } catch (err) {
    error.value = apiErr(err) ?? t('errors.generic')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="ph"><div><h1>{{ t('portal.nav.homework') }}</h1><p>{{ canSubmit ? t('portal.hw.subtitleStudent') : t('portal.hw.subtitleParent') }}</p></div></div>
  <div v-if="!items" class="card card-pad"><UiSkeleton :lines="5" /></div>
  <UiEmptyState v-else-if="!items.length" icon="homework" :title="t('portal.hw.none')" />
  <div v-else class="hw-list">
    <article v-for="h in items" :key="h.id" class="hw">
      <header>
        <div>
          <b>{{ h.title }}</b>
          <div class="muted" style="font-size: 12.5px" :class="{ redc: overdue(h) }">
            <template v-if="h.due_at">{{ t('portal.hw.due', { date: `${dayLabel(h.due_at, loc)} ${hm(h.due_at, loc)}` }) }}</template><template v-else>{{ t('portal.hw.noDue') }}</template>
          </div>
        </div>
        <div style="display: flex; gap: 6px; align-items: center">
          <span v-if="h.grade !== null" class="grade-pill" :title="t('portal.grade')">{{ h.grade }}</span>
          <UiChip :tone="overdue(h) ? 'red' : TONE[h.status]" small>{{ overdue(h) ? t('portal.hw.overdue') : statusLabel(h.status) }}</UiChip>
        </div>
      </header>
      <p v-if="h.body" class="m0 pre" style="font-size: 14px">{{ h.body }}</p>
      <div v-if="h.answer || h.file_url" class="fb-answer">
        <span class="fb-meta">{{ t('portal.hw.yourAnswer') }}</span>
        <p v-if="h.answer" class="m0 pre">{{ h.answer }}</p>
        <a v-if="safeUrl(h.file_url)" :href="safeUrl(h.file_url)!" target="_blank" rel="noopener" class="rowlink"><UiIcon name="clip" :size="14" /> {{ t('portal.hw.file') }}</a>
      </div>
      <div v-if="h.teacher_comment" class="fb-answer">
        <span class="fb-meta">{{ t('portal.hw.teacher') }}</span>
        <p class="m0 pre">{{ h.teacher_comment }}</p>
      </div>
      <template v-if="canSubmit && h.status !== 'checked'">
        <form v-if="openId === h.id" class="stack" @submit.prevent="submit(h)">
          <UiTextarea v-model="draft.answer" :label="t('portal.hw.answer')" :rows="4" :maxlength="8000" />
          <div class="file-pick">
            <label class="btn sm" :class="{ loading: uploading }"><UiIcon name="attach" :size="16" />{{ draft.file ? t('portal.hw.otherFile') : t('portal.hw.attach') }}<input type="file" class="sr" accept="image/*,application/pdf,.doc,.docx,audio/*" @change="pickFile" /></label>
            <span v-if="uploading" class="muted">{{ t('common.loading') }}</span>
            <span v-else-if="draft.file" class="chip"><UiIcon name="clip" :size="14" />{{ draft.file.name }}</span>
          </div>
          <p v-if="error" class="form-err" role="alert">{{ error }}</p>
          <div class="row-acts" style="justify-content: flex-start">
            <UiButton type="submit" variant="primary" icon="send" :loading="busy" :disabled="uploading">{{ t('portal.hw.send') }}</UiButton>
            <UiButton variant="ghost" @click="openId = null">{{ t('common.cancel') }}</UiButton>
          </div>
        </form>
        <div v-else><UiButton size="sm" :variant="h.status === 'assigned' ? 'navy' : 'default'" icon="edit" @click="start(h)">{{ h.status === 'assigned' ? t('portal.hw.do') : t('portal.hw.redo') }}</UiButton></div>
      </template>
    </article>
  </div>
</template>
