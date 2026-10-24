import { nextTick, ref, type Ref } from 'vue'

/** Keeps a message list pinned to the bottom unless the reader scrolled up. */
export function useAutoScroll(el: Ref<HTMLElement | null>) {
  const atBottom = ref(true)
  function onScroll() {
    const e = el.value
    if (e) atBottom.value = e.scrollHeight - e.scrollTop - e.clientHeight < 80
  }
  async function toBottom(force = false) {
    await nextTick()
    const e = el.value
    if (e && (force || atBottom.value)) e.scrollTop = e.scrollHeight
  }
  /** Prepend older items without jumping. */
  async function keepPosition(fn: () => void) {
    const e = el.value
    const before = e ? e.scrollHeight - e.scrollTop : 0
    fn()
    await nextTick()
    if (e) e.scrollTop = e.scrollHeight - before
  }
  return { atBottom, onScroll, toBottom, keepPosition }
}
