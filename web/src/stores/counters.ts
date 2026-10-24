import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * Unread counters for the sidebar (new leads, unanswered dialogs, chats, tasks).
 * Zero hides the badge. Filled once the backend exposes a counters endpoint.
 */
export const useCountersStore = defineStore('counters', () => {
  const counts = ref<Record<string, number>>({})
  const get = (key: string | undefined) => (key ? counts.value[key] ?? 0 : 0)
  function set(next: Record<string, number>) {
    counts.value = next
  }
  return { counts, get, set }
})
