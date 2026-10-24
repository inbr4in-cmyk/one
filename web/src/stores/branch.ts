import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { useAuthStore } from './auth'
import { readPref, writePref } from '@/utils/storage'

export interface BranchOption {
  /** null = the whole network */
  id: number | null
  /** i18n key under `branch.` */
  key: string
}

/**
 * Static until the backend exposes GET /api/branches.
 * Ids follow the seed order (1 = Янги шахар, 2 = Север).
 */
const BRANCHES: BranchOption[] = [
  { id: 1, key: 'yangi' },
  { id: 2, key: 'north' },
]
const ALL: BranchOption = { id: null, key: 'all' }
const KEY = 'oe-branch'

export const useBranchStore = defineStore('branch', () => {
  const auth = useAuthStore()
  const stored = readPref(KEY)
  const selectedId = ref<number | null>(stored === null || stored === 'all' ? null : Number(stored))

  const options = computed<BranchOption[]>(() => {
    if (auth.hasNetworkScope) return [...BRANCHES, ALL]
    const mine = auth.user?.branch_ids ?? []
    const list = BRANCHES.filter((b) => b.id !== null && mine.includes(b.id))
    return list.length ? list : BRANCHES
  })

  const current = computed<BranchOption>(
    () => options.value.find((o) => o.id === selectedId.value) ?? options.value[0] ?? ALL,
  )

  function select(id: number | null) {
    selectedId.value = id
  }

  watch(selectedId, (id) => writePref(KEY, id === null ? 'all' : String(id)))

  return { options, current, select }
})
