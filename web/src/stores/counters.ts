import { defineStore } from 'pinia'
import { ref } from 'vue'
import { notifyApi, type Counters } from '@/api/chats'
import { onRealtime } from '@/composables/useRealtime'

const POLL_MS = 30_000

/** Badge numbers (bell, Chats, Inbox): polled every 30 s and refreshed on realtime events. */
export const useCountersStore = defineStore('counters', () => {
  const counts = ref<Counters>({ notifications: 0 })
  let timer: ReturnType<typeof setInterval> | undefined
  let debounce: ReturnType<typeof setTimeout> | undefined
  let offs: (() => void)[] = []

  const get = (key: string | undefined) => (key ? (counts.value as unknown as Record<string, number | undefined>)[key] ?? 0 : 0)

  async function refresh() {
    try {
      counts.value = await notifyApi.counters()
    } catch {
      /* keep the last numbers */
    }
  }

  function soon() {
    clearTimeout(debounce)
    debounce = setTimeout(refresh, 400)
  }

  function start() {
    stop()
    refresh()
    timer = setInterval(() => document.visibilityState === 'visible' && refresh(), POLL_MS)
    offs = ['chat.message', 'inbox.message', 'notification', 'realtime.open'].map((t) => onRealtime(t, soon))
  }

  function stop() {
    clearInterval(timer)
    clearTimeout(debounce)
    offs.forEach((off) => off())
    offs = []
  }

  return { counts, get, refresh, start, stop }
})
