import { defineStore } from 'pinia'
import { ref } from 'vue'

export type ToastTone = 'info' | 'ok' | 'error'

export interface Toast {
  id: number
  text: string
  tone: ToastTone
}

const DURATION = 4000
const MAX = 3

export const useToastStore = defineStore('toast', () => {
  const items = ref<Toast[]>([])
  let seq = 0
  const timers = new Map<number, ReturnType<typeof setTimeout>>()

  function dismiss(id: number) {
    items.value = items.value.filter((t) => t.id !== id)
    clearTimeout(timers.get(id))
    timers.delete(id)
  }

  function show(text: string, tone: ToastTone = 'info', duration = DURATION) {
    // The same message twice in a row (e.g. several failed requests) is shown once.
    if (items.value.some((t) => t.text === text)) return
    const id = ++seq
    items.value = [...items.value.slice(-(MAX - 1)), { id, text, tone }]
    // duration 0 = stays until closed (save errors must not slip by unnoticed)
    if (duration > 0) timers.set(id, setTimeout(() => dismiss(id), duration))
  }

  return {
    items,
    show,
    dismiss,
    ok: (text: string) => show(text, 'ok'),
    error: (text: string) => show(text, 'error', 0),
  }
})
