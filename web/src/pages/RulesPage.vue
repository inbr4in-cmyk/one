<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiCard, UiChip, UiEmptyState, UiPrompt, UiSkeleton, UiTabs } from '@/components/ui'
import DocBody from '@/components/compliance/DocBody.vue'
import { docsApi, type DocKind, type DocumentVersion, type MyConsent } from '@/api/compliance'
import { portalApi, type PortalChild } from '@/api/portal'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import { dmy } from '@/utils/dates'
import type { Locale } from '@/i18n'

/** Platform rules and the lesson-recording consent: read, accept (parents sign the recording consent per child). */
const { t, locale } = useI18n()
const auth = useAuthStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)
const kind = ref<DocKind>('rules')
const docs = ref<Partial<Record<DocKind, DocumentVersion | null>>>({})
const children = ref<PortalChild[]>([])
const busy = ref<string | null>(null)
const consents = ref<MyConsent[]>([])
const revoking = ref<MyConsent | null>(null)

const tabs = computed(() => [{ value: 'rules' as const, label: t('rules.tab.rules') }, { value: 'recording' as const, label: t('rules.tab.recording') }])
const doc = computed(() => docs.value[kind.value])
const isParent = computed(() => auth.user?.kind === 'parent')
const rulesAccepted = computed(() => !!docs.value.rules && auth.user?.rules_accepted_version === docs.value.rules.version)

onMounted(async () => {
  const [r, c] = await Promise.all([docsApi.get('rules').catch(() => null), docsApi.get('recording').catch(() => null)])
  docs.value = { rules: r, recording: c }
  consents.value = await docsApi.my().catch(() => [])
  if (isParent.value) children.value = (await portalApi.me().catch(() => null))?.children ?? []
})

async function accept(studentId: number | null = null) {
  const d = doc.value
  if (!d) return
  const key = `${d.id}:${studentId ?? 'me'}`
  busy.value = key
  try {
    const r = await docsApi.accept(d.id, studentId)
    if (d.kind === 'rules' && auth.user) auth.user.rules_accepted_version = r.version
    consents.value = await docsApi.my().catch(() => consents.value)
    toast.ok(t('rules.accepted'))
  } finally {
    busy.value = null
  }
}
/** The active consent for the current document version, for me or for a child */
const consentFor = (studentId: number | null) => consents.value.find((c) => c.document_id === doc.value?.id && c.student_id === studentId && !c.revoked_at) ?? null
async function revoke() {
  const c = revoking.value
  if (!c) return
  busy.value = `revoke:${c.id}`
  try {
    await docsApi.revoke(c.id)
    consents.value = await docsApi.my().catch(() => consents.value)
    revoking.value = null
    toast.ok(t('rules.revoked'))
  } finally {
    busy.value = null
  }
}
</script>

<template>
  <div class="ph"><div><h1>{{ t('nav.rules') }}</h1><p>{{ t('rules.subtitle') }}</p></div></div>
  <div class="toolbar"><UiTabs v-model="kind" :items="tabs" :label="t('nav.rules')" /></div>

  <UiCard v-if="!(kind in docs)"><UiSkeleton :lines="6" /></UiCard>
  <UiEmptyState v-else-if="!doc" icon="file" :title="t('rules.notPublished')" />
  <div v-else class="grid fin-a rules-grid">
    <UiCard>
      <h2 class="doc-title">{{ doc.title }}</h2>
      <p class="muted" style="margin-top: 0; font-size: 13px">{{ t('rules.version', { v: doc.version, date: dmy(doc.effective_from, loc) }) }}</p>
      <div v-if="doc.upcoming" class="alert info"><span>{{ t('rules.upcoming', { v: doc.upcoming.version, date: dmy(doc.upcoming.effective_from, loc) }) }}</span></div>
      <DocBody :body="doc.body" />
    </UiCard>
    <UiCard :title="t('rules.yourConsent')">
      <template v-if="kind === 'rules'">
        <UiChip v-if="rulesAccepted" tone="ok" icon="ok">{{ t('rules.acceptedV', { v: doc.version }) }}</UiChip>
        <template v-else>
          <p class="muted" style="margin-top: 0">{{ t('rules.needAccept') }}</p>
          <UiButton variant="primary" :loading="busy !== null" @click="accept()">{{ t('rules.accept') }}</UiButton>
        </template>
      </template>
      <template v-else>
        <p class="muted" style="margin-top: 0">{{ isParent ? t('rules.recordingParent') : t('rules.recordingSelf') }}</p>
        <template v-if="isParent">
          <div v-for="c in children" :key="c.id" class="list-row">
            <div class="grow"><b>{{ c.full_name }}</b></div>
            <template v-if="consentFor(c.id)">
              <UiChip tone="ok" icon="ok" small :title="dmy(consentFor(c.id)!.accepted_at, loc)">{{ t('rules.signedAt', { date: dmy(consentFor(c.id)!.accepted_at, loc) }) }}</UiChip>
              <UiButton size="sm" variant="ghost" @click="revoking = consentFor(c.id)">{{ t('rules.revoke') }}</UiButton>
            </template>
            <UiButton v-else size="sm" variant="navy" :loading="busy === `${doc.id}:${c.id}`" @click="accept(c.id)">{{ t('rules.sign') }}</UiButton>
          </div>
        </template>
        <template v-else>
          <div v-if="consentFor(null)" class="chips-row">
            <UiChip tone="ok" icon="ok">{{ t('rules.signedAt', { date: dmy(consentFor(null)!.accepted_at, loc) }) }}</UiChip>
            <UiButton size="sm" variant="ghost" @click="revoking = consentFor(null)">{{ t('rules.revoke') }}</UiButton>
          </div>
          <UiButton v-else variant="navy" :loading="busy !== null" @click="accept()">{{ t('rules.sign') }}</UiButton>
        </template>
      </template>
    </UiCard>
  </div>
  <UiPrompt :open="!!revoking" :title="t('rules.revokeTitle')" :text="t('rules.revokeText')" :confirm-label="t('rules.revoke')" danger :busy="busy?.startsWith('revoke:')" @update:open="(v) => !v && (revoking = null)" @confirm="revoke" />
</template>
