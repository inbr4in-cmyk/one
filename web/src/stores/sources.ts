import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { sourcesApi, type SourceItem } from '@/api/crm'

/** «Откуда узнал» list, loaded once and shared by every picker; edited on the Справочники page. */
export const useSourcesStore = defineStore('sources', () => {
  const items = ref<SourceItem[]>([])
  let loading: Promise<void> | null = null
  function load(force = false): Promise<void> {
    if (!loading || force) {
      loading = sourcesApi.list().then((r) => void (items.value = r), () => void (loading = null))
    }
    return loading
  }
  const byCode = computed(() => new Map(items.value.map((s) => [s.code, s])))
  /** Choices for a picker: visible sources (a hidden one stays if it is the current value) */
  const options = (current?: string | null) =>
    items.value.filter((s) => !s.hidden || s.code === current).map((s) => ({ value: s.code, label: s.name }))
  return { items, load, byCode, options }
})
