<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { toDataURL } from 'qrcode'
import { UiButton, UiCard, UiChip, UiPrompt, UiSkeleton } from '@/components/ui'
import { adminApi, type WaLink } from '@/api/admin'
import { useToastStore } from '@/stores/toast'
import { apiErr } from '@/utils/err'

/** Settings: the school's WhatsApp linked by QR, like WhatsApp Web. Only the owner links and unlinks it. */
const { t } = useI18n()
const toast = useToastStore()
const link = ref<WaLink | null>(null)
const img = ref('')
const busy = ref(false)
const asking = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined
let alive = true

const waiting = computed(() => link.value?.state === 'qr' || link.value?.state === 'connecting')
const tone = computed(() => (link.value?.state === 'open' ? 'ok' : link.value?.state === 'banned' || link.value?.state === 'unavailable' ? 'red' : waiting.value ? 'warn' : 'info'))

watch(() => link.value?.qr, async (v) => {
  img.value = v ? await toDataURL(v, { margin: 1, width: 264 }).catch(() => '') : ''
})

function plan() {
  clearTimeout(timer)
  if (alive) timer = setTimeout(load, waiting.value ? 3000 : 30000)
}
async function load() {
  try {
    link.value = await adminApi.waLink()
  } catch {
    /* shown as it was; the next try is soon */
  }
  plan()
}
async function connect() {
  busy.value = true
  try {
    link.value = await adminApi.waLinkConnect()
    plan()
  } catch (e) {
    toast.error(apiErr(e) ?? t('errors.generic'))
  } finally {
    busy.value = false
  }
}
async function disconnect() {
  busy.value = true
  try {
    link.value = await adminApi.waLinkDisconnect()
    asking.value = false
    toast.show(t('nv.wa.unlinked'), 'ok')
    plan()
  } catch (e) {
    toast.error(apiErr(e) ?? t('errors.generic'))
  } finally {
    busy.value = false
  }
}
onMounted(load)
onBeforeUnmount(() => {
  alive = false
  clearTimeout(timer)
})
</script>

<template>
  <UiCard :title="t('nv.wa.title')" data-testid="wa-link">
    <UiSkeleton v-if="!link" :lines="3" />
    <div v-else class="stack wa-link">
      <div class="set-row">
        <div class="grow">
          <b>{{ link.state === 'open' && link.phone ? link.phone : t('nv.wa.number') }}</b>
          <span v-if="link.state === 'open' && link.name">{{ link.name }}</span>
        </div>
        <UiChip :tone="tone">{{ t(`nv.wa.state.${link.state}`) }}</UiChip>
      </div>
      <template v-if="link.can_manage">
        <div v-if="link.state === 'qr'" class="wa-qr">
          <img v-if="img" :src="img" width="264" height="264" :alt="t('nv.wa.qrAlt')" />
          <UiSkeleton v-else :lines="6" />
          <p>{{ t('nv.wa.how') }}</p>
        </div>
        <p v-if="link.state === 'banned'" class="form-err" role="alert">{{ t('nv.wa.bannedNote') }}</p>
        <p v-else-if="link.state === 'unavailable' || link.state === 'disabled'" class="form-err" role="alert">{{ t('nv.wa.downNote') }}</p>
        <div v-if="link.state === 'open' || link.state === 'connecting'">
          <UiButton icon="x" :loading="busy" @click="asking = true">{{ t('nv.wa.unlink') }}</UiButton>
        </div>
        <div v-else-if="['off', 'logged_out', 'banned'].includes(link.state)">
          <UiButton variant="navy" icon="chat" :loading="busy" data-testid="wa-connect" @click="connect">{{ t('nv.wa.connect') }}</UiButton>
        </div>
      </template>
    </div>
    <UiPrompt v-model:open="asking" :title="t('nv.wa.unlinkTitle')" :text="t('nv.wa.unlinkText')" :confirm-label="t('nv.wa.unlink')" danger :busy="busy" @confirm="disconnect" />
  </UiCard>
</template>

<style scoped>
.wa-qr { display: grid; justify-items: center; gap: 10px; padding: 8px 0; text-align: center; }
.wa-qr img { border-radius: 12px; background: #fff; padding: 8px; box-sizing: content-box; }
.wa-qr p { margin: 0; color: var(--muted, #6b7280); font-size: 13px; max-width: 320px; }
</style>
