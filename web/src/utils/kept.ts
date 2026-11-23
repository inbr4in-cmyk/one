import { reactive, toRef, type Ref } from 'vue'

/**
 * Filters of a list page that survive opening an item and coming back («Назад»).
 * Opening a section through the menu starts it clean: the menu calls resetKept().
 */
const store = new Map<string, object>()

export function kept<T extends object>(key: string, init: () => T): T {
  if (!store.has(key)) store.set(key, reactive(init()))
  return store.get(key) as T
}

export function keptRef<T>(key: string, init: () => T): Ref<T> {
  return toRef(kept(key, () => ({ v: init() })) as { v: T }, 'v')
}

export function resetKept(): void {
  store.clear()
}
