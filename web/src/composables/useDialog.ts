import { nextTick, onBeforeUnmount, watch, type Ref } from 'vue'

const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])'
let openCount = 0
/** Open dialogs, topmost last: Esc still closes the top one when focus fell back to <body>. */
const stack: (() => void)[] = []
function onDocKey(e: KeyboardEvent) {
  if (e.key !== 'Escape' || !stack.length) return
  const t = e.target as HTMLElement | null
  if (t && t !== document.body && t.closest('.ov')) return // handled by the dialog itself
  stack[stack.length - 1]?.()
}

/** Esc to close, focus moved in and trapped, focus restored, page scroll locked. */
export function useDialog(open: Ref<boolean>, box: Ref<HTMLElement | null>, close: () => void) {
  let restoreTo: HTMLElement | null = null

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      e.stopPropagation()
      close()
      return
    }
    if (e.key !== 'Tab' || !box.value) return
    const items = [...box.value.querySelectorAll<HTMLElement>(FOCUSABLE)]
    if (!items.length) return
    const first = items[0]!
    const last = items[items.length - 1]!
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault()
      first.focus()
    }
  }

  function lock(on: boolean) {
    if (on) stack.push(close)
    else {
      const i = stack.lastIndexOf(close)
      if (i >= 0) stack.splice(i, 1)
    }
    if (stack.length === 1 && on) document.addEventListener('keydown', onDocKey)
    if (!stack.length) document.removeEventListener('keydown', onDocKey)
    openCount += on ? 1 : -1
    document.documentElement.style.overflow = openCount > 0 ? 'hidden' : ''
  }

  watch(open, async (v, was) => {
    if (v) {
      restoreTo = document.activeElement as HTMLElement | null
      lock(true)
      await nextTick()
      const target = box.value?.querySelector<HTMLElement>('[autofocus]') ?? box.value?.querySelector<HTMLElement>(FOCUSABLE) ?? box.value
      target?.focus()
    } else if (was) {
      lock(false)
      restoreTo?.focus?.()
    }
  }, { immediate: true })

  onBeforeUnmount(() => {
    if (open.value) lock(false)
  })

  return { onKey }
}
