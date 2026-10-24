import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { useAuthStore } from './auth'
import { useRefsStore } from './refs'
import { readPref, writePref } from '@/utils/storage'

export interface BranchOption {
  /** null = the whole network */
  id: number | null
  name: string
}

const KEY = 'oe-branch'

/** The branch the screens are filtered by. Options come from GET /api/branches. */
export const useBranchStore = defineStore('branch', () => {
  const auth = useAuthStore()
  const refs = useRefsStore()
  const stored = readPref(KEY)
  const selectedId = ref<number | null>(stored === null || stored === 'all' ? null : Number(stored))

  const options = computed<BranchOption[]>(() => {
    const mine = auth.user?.branch_ids ?? []
    const list = refs.branches
      .filter((b) => auth.hasNetworkScope || mine.includes(b.id))
      .map((b) => ({ id: b.id, name: b.name }))
    return auth.hasNetworkScope && list.length > 1 ? [...list, { id: null, name: '' }] : list
  })

  const current = computed<BranchOption>(
    () => options.value.find((o) => o.id === selectedId.value) ?? options.value[0] ?? { id: null, name: '' },
  )
  /** Branch id to send as a filter (null = all branches the user may see). */
  const filterId = computed(() => current.value.id)

  function select(id: number | null) {
    selectedId.value = id
  }

  watch(selectedId, (id) => writePref(KEY, id === null ? 'all' : String(id)))

  return { options, current, filterId, select }
})
