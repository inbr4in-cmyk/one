<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiIcon } from '@/components/ui'

/** After a release everybody with the site open gets a small window «Доступна новая версия» with «Обновить» (owner, 21.11.2026). */
const { t } = useI18n()
const CHECK_MS = 60_000
const LATER_MS = 10 * 60_000
const open = ref(false)
const busy = ref(false)
let timer: ReturnType<typeof setInterval> | undefined
let snoozeUntil = 0

async function check() {
  if (open.value || import.meta.env.DEV || import.meta.env.VITE_DEMO === '1' || Date.now() < snoozeUntil) return
  try {
    const r = await fetch(`/version.json?t=${Date.now()}`, { cache: 'no-store' })
    if (!r.ok) return
    const v = (await r.json()) as { build?: string }
    if (v.build && v.build !== __BUILD_ID__) open.value = true
  } catch {
    /* offline: ask again later */
  }
}
function onVisible() {
  if (document.visibilityState === 'visible') void check()
}
function later() {
  open.value = false
  snoozeUntil = Date.now() + LATER_MS
}
async function update() {
  busy.value = true
  // The site's own cache is emptied (old styles, icons, scripts), the login and personal settings stay.
  try {
    if ('caches' in window) await Promise.all((await caches.keys()).map((k) => caches.delete(k)))
    const regs = (await navigator.serviceWorker?.getRegistrations()) ?? []
    await Promise.all(regs.map((r) => r.update().catch(() => undefined)))
  } catch {
    /* the reload below is enough */
  }
  const url = new URL(window.location.href)
  url.searchParams.set('v', String(Date.now())) // a fresh address: the browser asks the server for the page again
  window.location.replace(url.toString())
}
onMounted(() => {
  timer = setInterval(check, CHECK_MS)
  document.addEventListener('visibilitychange', onVisible)
  void check()
})
onBeforeUnmount(() => {
  clearInterval(timer)
  document.removeEventListener('visibilitychange', onVisible)
})
</script>

<template>
  <Teleport to="body">
    <Transition name="toast">
      <div v-if="open" class="upd" role="alertdialog" aria-labelledby="upd-h">
        <span class="upd-ico"><UiIcon name="zap" :size="20" /></span>
        <div class="grow"><b id="upd-h">{{ t('nv.upd.title') }}</b><span>{{ t('nv.upd.text') }}</span></div>
        <UiButton size="sm" variant="ghost" @click="later">{{ t('nv.upd.later') }}</UiButton>
        <UiButton size="sm" variant="primary" :loading="busy" @click="update">{{ t('nv.upd.update') }}</UiButton>
      </div>
    </Transition>
  </Teleport>
</template>
