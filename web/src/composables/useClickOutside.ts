import { onBeforeUnmount, onMounted, type Ref } from 'vue'

/** Calls `handler` on pointerdown outside every given element, and on Escape. */
export function useClickOutside(els: Ref<HTMLElement | null>[], handler: () => void) {
  function onDown(e: PointerEvent) {
    const target = e.target as Node
    if (els.every((el) => !el.value?.contains(target))) handler()
  }
  function onKey(e: KeyboardEvent) {
    if (e.key === 'Escape') handler()
  }
  onMounted(() => {
    document.addEventListener('pointerdown', onDown)
    document.addEventListener('keydown', onKey)
  })
  onBeforeUnmount(() => {
    document.removeEventListener('pointerdown', onDown)
    document.removeEventListener('keydown', onKey)
  })
}
