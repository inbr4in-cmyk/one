<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiAvatar, UiChip, UiInput, UiSkeleton } from '@/components/ui'
import { useRefsStore } from '@/stores/refs'

/** Pick several colleagues from the staff directory (task assignees). */
const props = defineProps<{ branchId?: number | null }>()
const model = defineModel<number[]>({ required: true })
const { t } = useI18n()
const refs = useRefsStore()
const q = ref('')
const loading = ref(true)
onMounted(async () => {
  await refs.loadStaff()
  loading.value = false
})
const list = computed(() => {
  const s = q.value.trim().toLowerCase()
  return refs.staff
    .filter((x) => !props.branchId || x.branch_ids.includes(props.branchId) || model.value.includes(x.id))
    .filter((x) => !s || x.full_name.toLowerCase().includes(s) || (x.position ?? '').toLowerCase().includes(s))
})
const picked = computed(() => model.value.map((id) => refs.staffById.get(id)).filter((x) => !!x))
const toggle = (id: number) => (model.value = model.value.includes(id) ? model.value.filter((x) => x !== id) : [...model.value, id])
</script>

<template>
  <div class="picker">
    <div v-if="picked.length" class="chips-row">
      <button v-for="p in picked" :key="p.id" type="button" class="chip-x" :aria-label="t('tasks.removeAssignee', { name: p.full_name })" @click="toggle(p.id)">
        <UiChip small>{{ p.full_name }} ×</UiChip>
      </button>
    </div>
    <UiInput v-model="q" type="search" icon="search" :placeholder="t('tasks.findPerson')" />
    <div class="picker-list short" role="listbox" aria-multiselectable="true">
      <template v-if="loading"><div v-for="i in 3" :key="i" class="list-row"><UiSkeleton width="60%" /></div></template>
      <button v-for="s in list" :key="s.id" type="button" role="option" class="list-row pick" :aria-selected="model.includes(s.id)" @click="toggle(s.id)">
        <span class="cbox" :class="{ on: model.includes(s.id) }" aria-hidden="true" />
        <UiAvatar :name="s.full_name" size="sm" />
        <div class="grow"><b>{{ s.full_name }}</b><span>{{ s.position ?? '—' }}</span></div>
      </button>
      <p v-if="!loading && !list.length" class="muted m0" style="padding: 10px 2px">{{ t('common.nothingFound') }}</p>
    </div>
  </div>
</template>
