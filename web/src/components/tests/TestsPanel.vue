<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { toDataURL } from 'qrcode'
import { UiButton, UiCard, UiChip, UiEmptyState, UiField, UiIcon, UiSelect, UiSkeleton } from '@/components/ui'
import TestDrawer from './TestDrawer.vue'
import { testsApi, type Test } from '@/api/assessment'
import { useAuthStore } from '@/stores/auth'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'

/** Обучение → Тесты: the list, the builder drawer and the branch QR link for the public placement test. */
const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const refs = useRefsStore()
const toast = useToastStore()

const canEdit = computed(() => auth.can('tests.edit'))
const tests = ref<Test[] | null>(null)
const drawer = ref(false)
const editing = ref<Test | null>(null)

const branchId = ref(0)
const qrLink = ref('')
const qrImg = ref('')
const branchOpts = computed(() => refs.branches.map((b) => ({ value: b.id, label: b.name })))
const hasPublishedPlacement = computed(() => (tests.value ?? []).some((x) => x.kind === 'placement' && x.is_published))

onMounted(async () => {
  await Promise.all([load(), refs.load()])
  branchId.value = refs.branches[0]?.id ?? 0
})

async function load() {
  tests.value = await testsApi.list().catch(() => [])
}

watch(branchId, async (id) => {
  qrLink.value = qrImg.value = ''
  if (!id) return
  try {
    const r = await testsApi.branchQr(id)
    // router.resolve keeps the link right for the hash-routed demo build too.
    qrLink.value = new URL(router.resolve(r.path).href, window.location.href).href
    // The printed code stays dark-on-white in every theme so any camera reads it.
    qrImg.value = await toDataURL(qrLink.value, { margin: 1, width: 480, errorCorrectionLevel: 'M', color: { dark: '#01225F', light: '#FFFFFF' } })
  } catch {
    /* toast shown by the client */
  }
})

function open(x: Test | null) {
  editing.value = x
  drawer.value = true
}
function onSaved(x: Test) {
  const list = tests.value ?? []
  const i = list.findIndex((y) => y.id === x.id)
  tests.value = i >= 0 ? list.map((y) => (y.id === x.id ? x : y)) : [...list, x]
  editing.value = x
}
async function copy() {
  try {
    await navigator.clipboard.writeText(qrLink.value)
    toast.ok(t('common.copied'))
  } catch {
    toast.error(t('errors.generic'))
  }
}
function download() {
  const a = document.createElement('a')
  a.href = qrImg.value
  a.download = `one-english-qr-${refs.branchName(branchId.value) || branchId.value}.png`
  a.click()
}
</script>

<template>
  <div class="grid">
    <UiCard :title="t('tests.qr.title')" icon="qr">
      <div class="qr-card">
        <div class="qr">
          <img v-if="qrImg" :src="qrImg" :alt="t('tests.qr.alt')" />
          <UiSkeleton v-else :lines="4" />
        </div>
        <div class="grow">
          <p class="m0 muted" style="font-size: 13.5px">{{ t('tests.qr.text') }}</p>
          <UiField v-if="branchOpts.length > 1" :label="t('tests.qr.branch')">
            <UiSelect v-model="branchId" :options="branchOpts" :label="t('tests.qr.branch')" block />
          </UiField>
          <div v-if="qrLink" class="qr-link">{{ qrLink }}</div>
          <div v-if="tests && !hasPublishedPlacement" class="alert" style="margin: 0"><UiIcon name="alert" :size="20" /><div class="grow"><span>{{ t('tests.qr.noPublished') }}</span></div></div>
          <div class="row-actions">
            <UiButton size="sm" icon="clip" :disabled="!qrLink" @click="copy">{{ t('tests.qr.copy') }}</UiButton>
            <UiButton size="sm" icon="dl" :disabled="!qrImg" @click="download">{{ t('tests.qr.download') }}</UiButton>
            <UiButton v-if="qrLink" size="sm" variant="ghost" icon="globe" :href="qrLink" target="_blank" rel="noopener">{{ t('tests.qr.open') }}</UiButton>
          </div>
        </div>
      </div>
    </UiCard>

    <div class="ph" style="margin: 4px 0 0">
      <div><h2 class="h-display" style="font-size: 18px; margin: 0">{{ t('tests.tab') }}</h2><p>{{ t('tests.subtitle') }}</p></div>
      <span class="sp" />
      <UiButton v-if="canEdit" variant="primary" icon="plus" @click="open(null)">{{ t('tests.new') }}</UiButton>
    </div>

    <div v-if="!tests" class="tst-list"><div v-for="i in 3" :key="i" class="card card-pad"><UiSkeleton :lines="2" /></div></div>
    <UiEmptyState v-else-if="!tests.length" icon="tests" :title="t('tests.empty')" :text="t('tests.emptyText')" />
    <div v-else class="tst-list">
      <button v-for="x in tests" :key="x.id" type="button" class="card tst-row" @click="open(x)">
        <span class="shop-ico" style="margin: 0"><UiIcon :name="x.kind === 'placement' ? 'qr' : 'tests'" :size="24" /></span>
        <div class="grow">
          <b>{{ x.title }}</b>
          <span class="chips-row">
            <UiChip small :tone="x.kind === 'placement' ? 'info' : undefined">{{ t(`tests.kind.${x.kind}`) }}</UiChip>
            <UiChip small :tone="x.is_published ? 'ok' : 'warn'">{{ x.is_published ? t('tests.published') : t('tests.draft') }}</UiChip>
            <span>{{ t('tests.questionsN', { n: x.questions }) }}</span>
            <span v-if="x.time_limit_min">· {{ t('placement.minutes', { n: x.time_limit_min }) }}</span>
          </span>
        </div>
        <UiIcon name="arrow" :size="16" class="muted" />
      </button>
    </div>
  </div>

  <TestDrawer v-model:open="drawer" :test="editing" :can-edit="canEdit" @saved="onSaved" />
</template>
