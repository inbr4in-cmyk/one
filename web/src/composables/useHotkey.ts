import { onBeforeUnmount, onMounted } from 'vue'

/** Ctrl/Cmd + key. Works on any keyboard layout (matches the physical key too, so Ctrl+К = Ctrl+K). */
export function useHotkey(key: string, handler: (e: KeyboardEvent) => void) {
  const code = `Key${key.toUpperCase()}`
  function onKey(e: KeyboardEvent) {
    if (!(e.ctrlKey || e.metaKey) || e.altKey) return
    if (e.key.toLowerCase() === key.toLowerCase() || e.code === code) {
      e.preventDefault()
      handler(e)
    }
  }
  onMounted(() => window.addEventListener('keydown', onKey))
  onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
}
