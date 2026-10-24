<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiChip, UiInput } from '@/components/ui'
import { searchApi, type SearchOut } from '@/api/chats'
import type { TaskLink } from '@/api/tasks'

/** Link a task to a student, lead or group via GET /search. */
const model = defineModel<{ type: TaskLink; id: number; title: string } | null>({ required: true })
const { t } = useI18n()
const q = ref('')
const out = ref<SearchOut>({})
let ctrl: AbortController | null = null
let timer: ReturnType<typeof setTimeout> | undefined
watch(q, (v) => {
  clearTimeout(timer)
  if (v.trim().length < 2) {
    out.value = {}
    return
  }
  timer = setTimeout(async () => {
    ctrl?.abort()
    ctrl = new AbortController()
    out.value = await searchApi.search(v.trim(), ctrl.signal).catch(() => ({}))
  }, 250)
})
const KINDS: { key: keyof SearchOut; type: TaskLink }[] = [{ key: 'students', type: 'student' }, { key: 'leads', type: 'lead' }, { key: 'groups', type: 'group' }]
const hits = computed(() => KINDS.flatMap((k) => (out.value[k.key] ?? []).slice(0, 4).map((h) => ({ ...h, type: k.type }))))
</script>

<template>
  <div v-if="model" class="chips-row">
    <UiChip icon="clip">{{ t(`tasks.link.${model.type}`) }}: {{ model.title }}</UiChip>
    <UiButton size="sm" variant="ghost" @click="model = null">{{ t('common.remove') }}</UiButton>
  </div>
  <div v-else class="picker">
    <UiInput v-model="q" type="search" icon="search" :placeholder="t('tasks.linkPh')" />
    <div v-if="hits.length" class="picker-list short" role="listbox">
      <button v-for="h in hits" :key="`${h.type}${h.id}`" type="button" role="option" class="list-row pick" @click="model = { type: h.type, id: h.id, title: h.title }">
        <div class="grow"><b>{{ h.title }}</b><span>{{ t(`tasks.link.${h.type}`) }}</span></div>
      </button>
    </div>
  </div>
</template>
