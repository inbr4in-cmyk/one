import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { portalApi, type PortalChild, type PortalMe } from '@/api/portal'
import { readPref, writePref } from '@/utils/storage'

const PREF = 'oe.portal.child'

/** Student / parent cabinet: who is signed in and which child the screens show. */
export const usePortalStore = defineStore('portal', () => {
  const me = ref<PortalMe | null>(null)
  const loading = ref(false)
  const failed = ref(false)
  const childId = ref<number | null>(Number(readPref(PREF)) || null)

  const children = computed(() => me.value?.children ?? [])
  const child = computed<PortalChild | null>(() => children.value.find((c) => c.id === childId.value) ?? children.value[0] ?? null)
  const isParent = computed(() => me.value?.kind === 'parent')
  /** Access paused for non-payment: only the overview, payments and documents stay open */
  const blocked = computed(() => !!child.value?.blocked)

  async function load() {
    loading.value = true
    failed.value = false
    try {
      me.value = await portalApi.me()
    } catch {
      failed.value = true
    } finally {
      loading.value = false
    }
  }
  function select(id: number) {
    childId.value = id
  }
  watch(childId, (v) => writePref(PREF, v ? String(v) : null))
  function reset() {
    me.value = null
  }

  return { me, loading, failed, children, child, childId, isParent, blocked, load, select, reset }
})
