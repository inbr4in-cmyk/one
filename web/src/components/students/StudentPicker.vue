<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiAvatar, UiInput, UiSkeleton } from '@/components/ui'
import { studentsApi, type StudentListItem } from '@/api/students'

/** Search box with a result list; emits the picked student. */
const props = defineProps<{ branchId?: number | null; exclude?: number[] }>()
const emit = defineEmits<{ pick: [StudentListItem] }>()
const { t } = useI18n()
const q = ref('')
const items = ref<StudentListItem[]>([])
const loading = ref(false)
let seq = 0
let timer: ReturnType<typeof setTimeout> | undefined

async function search() {
  const my = ++seq
  loading.value = true
  try {
    const page = await studentsApi.list({ q: q.value.trim() || undefined, branch_id: props.branchId ?? null, limit: 8 })
    if (my === seq) items.value = page.items.filter((s) => !props.exclude?.includes(s.id))
  } catch {
    if (my === seq) items.value = []
  } finally {
    if (my === seq) loading.value = false
  }
}
watch(q, () => {
  clearTimeout(timer)
  timer = setTimeout(search, 250)
}, { immediate: true })
</script>

<template>
  <div class="picker">
    <UiInput v-model="q" type="search" icon="search" :placeholder="t('students.searchPh')" autofocus />
    <div class="picker-list" role="listbox" :aria-busy="loading">
      <template v-if="loading && !items.length"><div v-for="i in 3" :key="i" class="list-row"><UiSkeleton width="60%" /></div></template>
      <button v-for="s in items" :key="s.id" type="button" role="option" class="list-row pick" @click="emit('pick', s)">
        <UiAvatar :name="s.full_name" size="sm" />
        <div class="grow"><b>{{ s.full_name }}</b><span>{{ s.group_names.join(', ') || t('students.noGroups') }}</span></div>
      </button>
      <p v-if="!loading && !items.length" class="muted m0" style="padding: 10px 2px">{{ t('common.nothingFound') }}</p>
    </div>
  </div>
</template>
