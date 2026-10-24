<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiCard, UiChip, UiEmptyState, UiField, UiInput, UiModal, UiSegmented, UiSkeleton, UiTextarea } from '@/components/ui'
import DocBody from '@/components/compliance/DocBody.vue'
import { docsApi, type DocKind, type DocumentVersion } from '@/api/compliance'
import { useAuthStore } from '@/stores/auth'
import { useBranchStore } from '@/stores/branch'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import { addDays, dmy, isoDate } from '@/utils/dates'
import { apiErr } from '@/utils/err'
import type { Locale } from '@/i18n'

/** Platform rules and recording consent: current versions, publishing a new one, who has not signed. */
const { t, locale } = useI18n()
const auth = useAuthStore()
const branch = useBranchStore()
const refs = useRefsStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)
const KINDS: DocKind[] = ['rules', 'recording']
const docs = ref<Partial<Record<DocKind, DocumentVersion | null>>>({})
const missing = ref<{ student_id: number; full_name: string; branch_id: number }[] | null>(null)
const viewing = ref<DocumentVersion | null>(null)
const publishing = ref(false)
const form = reactive({ kind: 'rules' as DocKind, version: '', title: '', body: '', effective_from: '' })
const error = ref<string | null>(null)
const busy = ref(false)
const kinds = computed(() => KINDS.map((k) => ({ value: k, label: t(`rules.tab.${k}`) })))
/** New rules apply no sooner than in 7 days once a version exists */
const minDate = computed(() => isoDate(addDays(new Date(), form.kind === 'rules' && docs.value.rules ? 7 : 0)))

async function loadDocs() {
  const [r, c] = await Promise.all(KINDS.map((k) => docsApi.get(k).catch(() => null)))
  docs.value = { rules: r, recording: c }
}
async function loadMissing() {
  if (!auth.can('students.view')) return
  missing.value = null
  missing.value = await docsApi.missing(branch.filterId).catch(() => [])
}
onMounted(() => {
  refs.load()
  loadDocs()
  loadMissing()
})
watch(() => branch.filterId, loadMissing)

function openPublish(kind: DocKind) {
  const cur = docs.value[kind]
  Object.assign(form, { kind, version: '', title: cur?.title ?? '', body: cur?.body ?? '', effective_from: '' })
  form.effective_from = minDate.value
  error.value = null
  publishing.value = true
}
watch(() => form.kind, () => {
  if (form.effective_from < minDate.value) form.effective_from = minDate.value
})

async function publish() {
  error.value = !form.version.trim() ? t('docs.versionRequired') : form.title.trim().length < 3 ? t('docs.titleRequired')
    : form.body.trim().length < 10 ? t('docs.bodyRequired') : !form.effective_from ? t('docs.dateRequired') : null
  if (error.value) return
  busy.value = true
  try {
    const today = isoDate(new Date())
    const at = form.effective_from === today ? new Date().toISOString() : new Date(`${form.effective_from}T00:00:00`).toISOString()
    await docsApi.publish({ kind: form.kind, version: form.version.trim(), title: form.title.trim(), body: form.body.trim(), effective_from: at })
    toast.ok(t('docs.published'))
    publishing.value = false
    await loadDocs()
    if (form.kind === 'recording') loadMissing()
  } catch (e) {
    error.value = apiErr(e) ?? t('errors.generic')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="ph"><div><h1>{{ t('nav.documents') }}</h1><p>{{ t('docs.subtitle') }}</p></div></div>

  <div class="grid fin-a">
    <div class="grid" style="align-content: start; grid-template-columns: minmax(0, 1fr)">
      <UiCard v-for="k in KINDS" :key="k" :title="t(`rules.tab.${k}`)">
        <template v-if="auth.can('settings.edit')" #actions><UiButton size="sm" icon="plus" @click="openPublish(k)">{{ t('docs.newVersion') }}</UiButton></template>
        <UiSkeleton v-if="!(k in docs)" :lines="2" />
        <p v-else-if="!docs[k]" class="muted m0">{{ t('rules.notPublished') }}</p>
        <template v-else>
          <div class="list-row" style="padding-top: 0">
            <div class="grow"><b>{{ docs[k]!.title }}</b><span>{{ t('rules.version', { v: docs[k]!.version, date: dmy(docs[k]!.effective_from, loc) }) }}</span></div>
            <UiButton size="sm" variant="ghost" icon="eye" @click="viewing = docs[k]!">{{ t('docs.view') }}</UiButton>
          </div>
          <UiChip v-if="docs[k]!.upcoming" tone="info" icon="clock">{{ t('rules.upcoming', { v: docs[k]!.upcoming!.version, date: dmy(docs[k]!.upcoming!.effective_from, loc) }) }}</UiChip>
        </template>
      </UiCard>
    </div>
    <UiCard v-if="auth.can('students.view')" :title="t('docs.missing')">
      <template v-if="missing?.length" #actions><span class="chip">{{ missing.length }}</span></template>
      <UiSkeleton v-if="!missing" :lines="4" />
      <UiEmptyState v-else-if="!missing.length" icon="ok" :title="docs.recording ? t('docs.allSigned') : t('docs.noRecording')" />
      <div v-else class="short-list">
        <RouterLink v-for="s in missing" :key="s.student_id" :to="`/students/${s.student_id}`" class="list-row">
          <div class="grow"><b>{{ s.full_name }}</b><span>{{ refs.branchName(s.branch_id) }}</span></div>
        </RouterLink>
      </div>
      <p class="muted" style="font-size: 12.5px; margin: 12px 0 0">{{ t('docs.missingNote') }}</p>
    </UiCard>
  </div>

  <UiModal :open="!!viewing" :title="viewing?.title" wide @update:open="(v) => !v && (viewing = null)">
    <DocBody v-if="viewing" :body="viewing.body" />
  </UiModal>

  <UiModal v-model:open="publishing" :title="t('docs.publishTitle')" wide>
    <form id="doc-form" class="stack" @submit.prevent="publish">
      <UiSegmented v-model="form.kind" :options="kinds" :label="t('docs.kind')" block />
      <div class="form-2">
        <UiInput v-model="form.version" :label="t('docs.version')" :placeholder="t('docs.versionPh')" :maxlength="16" />
        <UiField :label="t('docs.effective')" :hint="form.kind === 'rules' && docs.rules ? t('docs.sevenDays') : undefined">
          <input v-model="form.effective_from" type="date" class="inp" :min="minDate" :aria-label="t('docs.effective')" />
        </UiField>
      </div>
      <UiInput v-model="form.title" :label="t('docs.title')" :maxlength="255" />
      <UiTextarea v-model="form.body" :label="t('docs.body')" :hint="t('docs.bodyHint')" :rows="12" :maxlength="100000" />
      <p class="form-note">{{ t('docs.publishNote') }}</p>
      <p v-if="error" class="form-err" role="alert">{{ error }}</p>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton type="submit" form="doc-form" variant="primary" :loading="busy">{{ t('docs.publish') }}</UiButton>
    </template>
  </UiModal>
</template>
