<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { UiAvatar, UiButton, UiEmptyState, UiIcon, UiPrompt, UiSegmented, UiSkeleton } from '@/components/ui'
import ContactsModal from '@/components/chat/ContactsModal.vue'
import { chatsApi, type Chat, type ChatMessage } from '@/api/chats'
import { ApiError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { useBranchStore } from '@/stores/branch'
import { useCountersStore } from '@/stores/counters'
import { useToastStore } from '@/stores/toast'
import { useRealtime } from '@/composables/useRealtime'
import { useAutoScroll } from '@/composables/useAutoScroll'
import { dayTitle, hm, withDays } from '@/utils/dates'
import { relativeTime } from '@/utils/format'
import type { Locale } from '@/i18n'

const MAX_FILE = 20 * 1024 * 1024

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const branch = useBranchStore()
const counters = useCountersStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)

const mode = ref<'mine' | 'monitor'>('mine')
const chats = ref<Chat[]>([])
const monitorChats = ref<Chat[]>([])
const loading = ref(true)
const q = ref('')
const messages = ref<ChatMessage[]>([])
const pinned = ref<ChatMessage[]>([])
const msgsLoading = ref(false)
const hasMore = ref(false)
const text = ref('')
const sending = ref(false)
const uploading = ref(false)
const contactsOpen = ref(false)
const hiding = ref<ChatMessage | null>(null)
const pinIdx = ref(0)
const fileInput = ref<HTMLInputElement | null>(null)
const msgsEl = ref<HTMLElement | null>(null)
const { onScroll, toBottom, keepPosition } = useAutoScroll(msgsEl)

const me = computed(() => auth.user?.id)
const id = computed(() => (route.params.id ? Number(route.params.id) : null))
const canMonitor = computed(() => auth.can('chats.monitor'))
const current = computed(() => chats.value.find((c) => c.id === id.value) ?? monitorChats.value.find((c) => c.id === id.value) ?? null)
/** Viewing a chat the user is not a member of: read-only, audited by the server. */
const monitoring = computed(() => id.value !== null && !chats.value.some((c) => c.id === id.value))
const source = computed(() => (mode.value === 'monitor' ? monitorChats.value : chats.value))
const filtered = computed(() => {
  const s = q.value.trim().toLowerCase()
  return source.value.filter((c) => !s || c.title.toLowerCase().includes(s) || (c.last_message?.text ?? '').toLowerCase().includes(s))
})
const groups = computed(() => filtered.value.filter((c) => c.kind === 'group'))
const directs = computed(() => filtered.value.filter((c) => c.kind === 'direct'))
const thread = computed(() => withDays(messages.value))
const modeOptions = computed(() => [{ value: 'mine' as const, label: t('chats.mine') }, { value: 'monitor' as const, label: t('chats.monitor') }])
const pin = computed(() => pinned.value[pinIdx.value % Math.max(1, pinned.value.length)])

async function loadList() {
  try {
    chats.value = await chatsApi.list()
  } catch {
    /* toast */
  } finally {
    loading.value = false
  }
}
async function loadMonitor() {
  if (!canMonitor.value) return
  monitorChats.value = await chatsApi.monitor({ branch_id: branch.filterId }).catch(() => [])
}
watch(mode, (m) => m === 'monitor' && loadMonitor())
watch(() => branch.filterId, () => mode.value === 'monitor' && loadMonitor())

async function openChat(cid: number | null) {
  messages.value = []
  pinned.value = []
  text.value = ''
  pinIdx.value = 0
  if (!cid) return
  msgsLoading.value = true
  try {
    const [m, p] = await Promise.all([chatsApi.messages(cid), chatsApi.pinned(cid).catch(() => [])])
    if (id.value !== cid) return
    messages.value = m
    pinned.value = p
    hasMore.value = m.length >= 50
    const row = chats.value.find((c) => c.id === cid)
    if (row) row.unread = 0
    counters.refresh()
    toBottom(true)
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) router.replace('/chats')
  } finally {
    msgsLoading.value = false
  }
}
watch(id, openChat)
onMounted(async () => {
  await loadList()
  if (id.value && monitoring.value && canMonitor.value) {
    mode.value = 'monitor'
    await loadMonitor()
  }
  openChat(id.value)
})

async function older() {
  const first = messages.value[0]
  if (!id.value || !first) return
  const m = await chatsApi.messages(id.value, { before_id: first.id }).catch(() => [])
  hasMore.value = m.length >= 50
  keepPosition(() => (messages.value = [...m, ...messages.value]))
}

function upsertMessage(m: ChatMessage) {
  const i = messages.value.findIndex((x) => x.id === m.id)
  if (i >= 0) messages.value[i] = m
  else {
    messages.value = [...messages.value, m]
    toBottom(m.sender_id === me.value)
  }
}
function bumpList(chatId: number, m: ChatMessage, unread: boolean) {
  const row = chats.value.find((c) => c.id === chatId)
  if (!row) return loadList()
  row.last_message = { text: m.text ?? m.file_name ?? '', at: m.at, sender: m.sender_name }
  if (unread) row.unread++
  chats.value = [row, ...chats.value.filter((c) => c !== row)]
}

async function send(extra?: { file_key: string; file_name: string; kind: ChatMessage['kind'] }) {
  const cid = id.value
  const body = text.value.trim()
  if (!cid || (!body && !extra) || sending.value) return
  sending.value = true
  try {
    const m = await chatsApi.send(cid, { text: extra ? body || null : body, ...extra })
    upsertMessage(m)
    bumpList(cid, m, false)
    text.value = ''
  } catch {
    /* toast with the server's reason */
  } finally {
    sending.value = false
  }
}
function onKey(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    send()
  }
}

async function onFile(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  input.value = ''
  if (!f) return
  if (f.size > MAX_FILE) {
    toast.error(t('chats.tooBig', { mb: 20 }))
    return
  }
  uploading.value = true
  try {
    const up = await chatsApi.upload(f)
    await send({ file_key: up.key, file_name: up.name, kind: f.type.startsWith('image/') ? 'image' : 'file' })
  } catch {
    /* toast */
  } finally {
    uploading.value = false
  }
}

async function togglePin(m: ChatMessage) {
  const fresh = await chatsApi.pin(m.id).catch(() => null)
  if (!fresh) return
  upsertMessage(fresh)
  pinned.value = fresh.pinned ? [fresh, ...pinned.value.filter((p) => p.id !== fresh.id)] : pinned.value.filter((p) => p.id !== fresh.id)
  toast.ok(fresh.pinned ? t('chats.pinned') : t('chats.unpinned'))
}
async function hide() {
  const m = hiding.value
  if (!m) return
  try {
    await chatsApi.hide(m.id)
    messages.value = messages.value.filter((x) => x.id !== m.id)
    pinned.value = pinned.value.filter((x) => x.id !== m.id)
    hiding.value = null
  } catch {
    /* toast */
  }
}
function jumpTo(m: ChatMessage) {
  document.getElementById(`m${m.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  pinIdx.value++
}

useRealtime('chat.message', (e) => {
  const m = e.message as ChatMessage
  const chatId = Number(e.chat_id)
  const open = chatId === id.value
  if (open) {
    upsertMessage(m)
    if (document.visibilityState === 'visible') chatsApi.read(chatId)
  }
  if (m.sender_id !== me.value || !open) bumpList(chatId, m, !open && m.sender_id !== me.value)
})
useRealtime('realtime.open', async (e) => {
  if (!e.reconnect) return
  await loadList()
  const last = messages.value[messages.value.length - 1]
  if (id.value && last) (await chatsApi.messages(id.value, { after_id: last.id }).catch(() => [])).forEach(upsertMessage)
})

const ROLE: Record<string, string> = { staff: 'm', student: 's', parent: 'p' }
const roleOf = (c: Chat) => c.other_user?.kind
const subtitle = computed(() => {
  const c = current.value
  if (!c) return ''
  if (c.kind === 'group') return t('chats.members', { n: c.members })
  return c.other_user?.position ?? (c.other_user ? t(`chats.kind.${c.other_user.kind}`) : '')
})
const isImage = (m: ChatMessage) => m.kind === 'image' && m.file_url
</script>

<template>
  <div class="card inbox chats" :class="{ sel: id !== null }">
    <div class="ib-list">
      <div class="hd">
        <div class="ib-title">
          <h2 class="h-display">{{ t('nav.chats') }}</h2>
          <span class="sp" />
          <UiButton v-if="mode === 'mine'" size="sm" variant="ghost" icon="plus" :aria-label="t('chats.newChat')" :title="t('chats.newChat')" @click="contactsOpen = true" />
        </div>
        <label class="search ib-search"><UiIcon name="search" :size="16" /><input v-model="q" type="search" :placeholder="t('chats.searchPh')" :aria-label="t('top.search')" /></label>
        <UiSegmented v-if="canMonitor" v-model="mode" :options="modeOptions" :label="t('nav.chats')" size="sm" block />
      </div>
      <div class="items">
        <template v-if="loading"><div v-for="i in 5" :key="i" class="dlg"><UiSkeleton circle width="40px" height="40px" /><div class="grow"><UiSkeleton :lines="2" /></div></div></template>
        <template v-else>
          <template v-for="sec in [{ k: 'groups', items: groups }, { k: 'direct', items: directs }]" :key="sec.k">
            <div v-if="sec.items.length" class="grp-h">{{ t(`chats.${sec.k}`) }}</div>
            <RouterLink v-for="c in sec.items" :key="c.id" :to="`/chats/${c.id}`" class="dlg" :class="{ on: c.id === id }">
              <span v-if="c.kind === 'group'" class="av gav-av">{{ c.title.slice(0, 2) }}</span>
              <UiAvatar v-else :name="c.title" />
              <div class="grow">
                <div class="l1">
                  <b>{{ c.title }}</b>
                  <span v-if="roleOf(c)" class="role" :class="ROLE[roleOf(c)!]">{{ t(`chats.kind.${roleOf(c)}`) }}</span>
                  <time v-else-if="c.last_message">{{ relativeTime(c.last_message.at, loc) }}</time>
                </div>
                <div class="l2">
                  <p><template v-if="c.last_message?.sender && c.kind === 'group'">{{ c.last_message.sender }}: </template>{{ c.last_message?.text ?? '' }}</p>
                  <span v-if="c.unread && mode === 'mine'" class="badge soft">{{ c.unread }}</span>
                </div>
              </div>
            </RouterLink>
          </template>
          <UiEmptyState v-if="!filtered.length" icon="chat" :title="t('chats.empty')" :text="mode === 'mine' ? t('chats.emptyText') : undefined" />
        </template>
      </div>
    </div>

    <div class="ib-chat">
      <template v-if="id">
        <div class="hd">
          <UiButton class="back-btn" size="sm" variant="ghost" icon="arrow" :aria-label="t('common.back')" to="/chats" />
          <span v-if="current?.kind === 'group'" class="av gav-av">{{ current.title.slice(0, 2) }}</span>
          <UiAvatar v-else :name="current?.title ?? '·'" />
          <div class="grow"><b>{{ current?.title ?? '…' }}</b><span>{{ subtitle }}</span></div>
          <UiButton v-if="current?.group_id && auth.can('schedule.view')" size="sm" icon="groups" :to="`/groups/${current.group_id}`"><span class="cta-t">{{ t('chats.group') }}</span></UiButton>
        </div>
        <div v-if="monitoring" class="monitor-bar" role="status"><UiIcon name="eye" :size="18" /><span>{{ t('chats.monitorBanner') }}</span></div>
        <Transition name="fade">
          <button v-if="pin" type="button" class="pinned" @click="jumpTo(pin)">
            <UiIcon name="pin" :size="18" />
            <div class="grow"><b>{{ t('chats.pinnedTitle') }}<template v-if="pinned.length > 1"> · {{ (pinIdx % pinned.length) + 1 }}/{{ pinned.length }}</template></b>{{ pin.text ?? pin.file_name }}</div>
          </button>
        </Transition>
        <div ref="msgsEl" class="msgs" aria-live="polite" @scroll="onScroll">
          <button v-if="hasMore" type="button" class="day more-btn" @click="older">{{ t('chats.older') }}</button>
          <div v-if="msgsLoading" class="stack"><UiSkeleton v-for="i in 4" :key="i" :width="`${40 + i * 10}%`" height="38px" /></div>
          <template v-for="m in thread" :key="m.id">
            <span v-if="m.newDay" class="day">{{ dayTitle(m.at, loc, t('chats.today'), t('chats.yesterday')) }}</span>
            <div :id="`m${m.id}`" class="gm" :class="{ me: m.sender_id === me }">
              <UiAvatar v-if="m.sender_id !== me && current?.kind === 'group'" :name="m.sender_name ?? '?'" size="sm" />
              <div class="b" :class="[m.sender_id === me ? 'out' : 'in', { hiddenmsg: m.hidden, pinnedmsg: m.pinned }]">
                <span v-if="m.sender_id !== me && current?.kind === 'group'" class="by" style="display: flex; gap: 6px; align-items: center">
                  {{ m.sender_name }}<span v-if="m.sender_kind" class="role" :class="ROLE[m.sender_kind]">{{ t(`chats.kind.${m.sender_kind}`) }}</span>
                </span>
                <span v-if="m.hidden" class="hid-tag"><UiIcon name="eye" :size="14" />{{ t('chats.hiddenByAuthor') }}</span>
                <a v-if="isImage(m)" :href="m.file_url!" target="_blank" rel="noopener"><img :src="m.file_url!" :alt="m.file_name ?? ''" class="photo" loading="lazy" /></a>
                <a v-else-if="m.file_url" :href="m.file_url" target="_blank" rel="noopener" class="file">
                  <span class="fi">{{ (m.file_name?.split('.').pop() ?? 'FILE').slice(0, 4).toUpperCase() }}</span>
                  <b style="font-size: 13px">{{ m.file_name ?? t('chats.file') }}</b>
                </a>
                <span v-if="m.text" class="pre">{{ m.text }}</span>
                <time><UiIcon v-if="m.pinned" name="pin" :size="11" /> {{ hm(m.at, loc) }}<template v-if="m.edited"> · {{ t('chats.edited') }}</template></time>
                <span v-if="!monitoring" class="msg-acts">
                  <button v-if="auth.can('chats.pin') && current?.kind === 'group'" type="button" :aria-label="m.pinned ? t('chats.unpin') : t('chats.pin')" :title="m.pinned ? t('chats.unpin') : t('chats.pin')" @click="togglePin(m)"><UiIcon name="pin" :size="14" /></button>
                  <button v-if="m.sender_id === me" type="button" :aria-label="t('chats.hide')" :title="t('chats.hide')" @click="hiding = m"><UiIcon name="delete" :size="14" /></button>
                </span>
              </div>
            </div>
          </template>
          <div v-if="!msgsLoading && !messages.length" class="sys"><UiIcon name="chat" :size="18" /><div>{{ t('chats.noMessages') }}</div></div>
        </div>
        <div v-if="!monitoring" class="composer">
          <div class="cin">
            <input ref="fileInput" type="file" class="sr" accept="image/*,application/pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,audio/*" @change="onFile" />
            <button type="button" class="iconbtn" :aria-label="t('chats.attach')" :title="t('chats.attach')" :disabled="uploading" @click="fileInput?.click()">
              <span v-if="uploading" class="spin" aria-hidden="true" /><UiIcon v-else name="clip" />
            </button>
            <textarea v-model="text" rows="1" :placeholder="current ? t('chats.messageTo', { name: current.title }) : t('chats.message')" :aria-label="t('chats.message')" maxlength="4000" @keydown="onKey" />
            <button type="button" class="send" :aria-label="t('chats.send')" :disabled="!text.trim() || sending" @click="send()"><UiIcon name="send" /></button>
          </div>
        </div>
      </template>
      <UiEmptyState v-else large icon="chat" :title="t('chats.pick')" :text="t('chats.pickText')" />
    </div>
  </div>
  <ContactsModal v-model:open="contactsOpen" @opened="(c) => { loadList(); router.push(`/chats/${c.id}`) }" />
  <UiPrompt :open="hiding !== null" :title="t('chats.hide')" :text="t('chats.hideText')" :confirm-label="t('chats.hide')" danger @update:open="(v) => !v && (hiding = null)" @confirm="hide" />
</template>
