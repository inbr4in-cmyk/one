<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiAvatar, UiInput, UiModal, UiSkeleton } from '@/components/ui'
import { chatsApi, type Chat, type ChatUser } from '@/api/chats'

/** People the user may write to (the server applies the child-safety rules). */
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ opened: [Chat] }>()
const { t } = useI18n()
const q = ref('')
const items = ref<ChatUser[]>([])
const loading = ref(false)
const busyId = ref<number | null>(null)
let timer: ReturnType<typeof setTimeout> | undefined
let seq = 0

async function search() {
  const my = ++seq
  loading.value = true
  try {
    const r = await chatsApi.contacts(q.value.trim() || undefined)
    if (my === seq) items.value = r
  } catch {
    if (my === seq) items.value = []
  } finally {
    if (my === seq) loading.value = false
  }
}
watch(open, (v) => {
  if (v) {
    q.value = ''
    search()
  }
})
watch(q, () => {
  clearTimeout(timer)
  timer = setTimeout(search, 250)
})

async function pick(u: ChatUser) {
  busyId.value = u.id
  try {
    const chat = await chatsApi.direct(u.id)
    emit('opened', chat)
    open.value = false
  } catch {
    /* the 403 reason (e.g. child-safety rule) is shown as a toast */
  } finally {
    busyId.value = null
  }
}
</script>

<template>
  <UiModal v-model:open="open" :title="t('chats.newChat')">
    <div class="picker">
      <UiInput v-model="q" type="search" icon="search" :placeholder="t('chats.contactsPh')" autofocus />
      <div class="picker-list" role="listbox" :aria-busy="loading">
        <template v-if="loading && !items.length"><div v-for="i in 4" :key="i" class="list-row"><UiSkeleton width="60%" /></div></template>
        <button v-for="u in items" :key="u.id" type="button" role="option" class="list-row pick" :disabled="busyId !== null" @click="pick(u)">
          <UiAvatar :name="u.full_name" size="sm" />
          <div class="grow"><b>{{ u.full_name }}</b><span>{{ u.position ?? t(`chats.kind.${u.kind}`) }}</span></div>
          <span v-if="busyId === u.id" class="spin" aria-hidden="true" />
        </button>
        <p v-if="!loading && !items.length" class="muted m0" style="padding: 10px 2px">{{ t('common.nothingFound') }}</p>
      </div>
    </div>
  </UiModal>
</template>
