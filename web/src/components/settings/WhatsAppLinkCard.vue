<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { toDataURL } from 'qrcode'
import { UiButton, UiCard, UiChip, UiPrompt, UiSkeleton } from '@/components/ui'
import { adminApi, type WaLink } from '@/api/admin'
import { useToastStore } from '@/stores/toast'
import { apiErr } from '@/utils/err'

/** Settings: the school's WhatsApp numbers linked by QR, like WhatsApp Web — one per branch. Only the owner links
 * and unlinks them. */
const { t } = useI18n()
const toast = useToastStore()
const links = ref<WaLink[] | null>(null)
const imgs = reactive<Record<number, string>>({})
const busy = ref<number | null>(null)
const asking = ref<number | null>(null)
let timer: ReturnType<typeof setTimeout> | undefined
let alive = true

const isWaiting = (l: WaLink) => l.state === 'qr' || l.state === 'connecting'
const waiting = computed(() => (links.value ?? []).some(isWaiting))
const tone = (l: WaLink) => (l.state === 'open' ? 'ok' : l.state === 'banned' || l.state === 'unavailable' ? 'red' : isWaiting(l) ? 'warn' : 'info')

watch(links, async (list) => {
  for (const l of list ?? []) imgs[l.line] = l.qr ? await toDataURL(l.qr, { margin: 1, width: 264 }).catch(() => '') : ''
})

function plan() {
  clearTimeout(timer)
  if (alive) timer = setTimeout(load, waiting.value ? 3000 : 30000)
}
async function load() {
  try {
    links.value = await adminApi.waLinks()
  } catch {
    /* shown as it was; the next try is soon */
  }
  plan()
}
function put(l: WaLink) {
  links.value = (links.value ?? []).map((x) => (x.line === l.line ? l : x))
  plan()
}
async function connect(line: number) {
  busy.value = line
  try {
    put(await adminApi.waLinkConnect(line))
  } catch (e) {
    toast.error(apiErr(e) ?? t('errors.generic'))
  } finally {
    busy.value = null
  }
}
async function disconnect() {
  const line = asking.value
  if (line === null) return
  busy.value = line
  try {
    put(await adminApi.waLinkDisconnect(line))
    asking.value = null
    toast.show(t('nv.wa.unlinked'), 'ok')
  } catch (e) {
    toast.error(apiErr(e) ?? t('errors.generic'))
  } finally {
    busy.value = null
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
    <UiSkeleton v-if="!links" :lines="3" />
    <div v-else class="stack wa-link">
      <div v-for="link in links" :key="link.line" class="stack wa-line" :data-testid="`wa-line-${link.line}`">
        <div class="set-row">
          <div class="grow">
            <b>{{ link.branch ?? t('nv.wa.number') }}</b>
            <span v-if="link.state === 'open' && link.phone">{{ link.phone }}<template v-if="link.name"> · {{ link.name }}</template></span>
          </div>
          <UiChip :tone="tone(link)">{{ t(`nv.wa.state.${link.state}`) }}</UiChip>
        </div>
        <template v-if="link.can_manage">
          <div v-if="link.state === 'qr'" class="wa-qr">
            <img v-if="imgs[link.line]" :src="imgs[link.line]" width="264" height="264" :alt="t('nv.wa.qrAlt')" />
            <UiSkeleton v-else :lines="6" />
            <p>{{ t('nv.wa.how') }}</p>
          </div>
          <p v-if="link.state === 'banned'" class="form-err" role="alert">{{ t('nv.wa.bannedNote') }}</p>
          <p v-else-if="link.state === 'unavailable' || link.state === 'disabled'" class="form-err" role="alert">{{ t('nv.wa.downNote') }}</p>
          <div v-if="link.state === 'open' || link.state === 'connecting'">
            <UiButton icon="x" :loading="busy === link.line" @click="asking = link.line">{{ t('nv.wa.unlink') }}</UiButton>
          </div>
          <div v-else-if="['off', 'logged_out', 'banned'].includes(link.state)">
            <UiButton variant="navy" icon="chat" :loading="busy === link.line" data-testid="wa-connect" @click="connect(link.line)">{{ t('nv.wa.connect') }}</UiButton>
          </div>
        </template>
      </div>
    </div>
    <UiPrompt :open="asking !== null" :title="t('nv.wa.unlinkTitle')" :text="t('nv.wa.unlinkText')" :confirm-label="t('nv.wa.unlink')" danger :busy="busy !== null" @update:open="(v: boolean) => { if (!v) asking = null }" @confirm="disconnect" />
  </UiCard>
</template>

<style scoped>

.wa-line + .wa-line { border-top: 1px solid var(--line, #e5e7eb); padding-top: 14px; }
.wa-qr { display: grid; justify-items: center; gap: 10px; padding: 8px 0; text-align: center; }
.wa-qr img { border-radius: 12px; background: #fff; padding: 8px; box-sizing: content-box; }
.wa-qr p { margin: 0; color: var(--muted, #6b7280); font-size: 13px; max-width: 320px; }
</style>
