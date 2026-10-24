<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { UiAvatar, UiButton, UiChip, UiEmptyState, UiIcon, UiSegmented, UiSkeleton } from '@/components/ui'
import TemplateModal from '@/components/chat/TemplateModal.vue'
import { inboxApi, type Channel, type Conversation, type InboxMessage } from '@/api/inbox'
import { ApiError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { useCountersStore } from '@/stores/counters'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import { useRealtime } from '@/composables/useRealtime'
import { useAutoScroll } from '@/composables/useAutoScroll'
import { dayTitle, hm, withDays } from '@/utils/dates'
import { relativeTime } from '@/utils/format'
import { formatPhone } from '@/utils/phone'
import type { Locale } from '@/i18n'

const { t, te, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const counters = useCountersStore()
const refs = useRefsStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)

const list = ref<Conversation[]>([])
const listLoading = ref(true)
const channel = ref<'' | Channel>('')
const unreadOnly = ref(false)
const mine = ref(false)
const q = ref('')
const conv = ref<Conversation | null>(null)
const messages = ref<InboxMessage[]>([])
const msgsLoading = ref(false)
const hasMore = ref(false)
const text = ref('')
const sending = ref(false)
const tplOpen = ref(false)
const msgsEl = ref<HTMLElement | null>(null)
const { onScroll, toBottom, keepPosition } = useAutoScroll(msgsEl)

const id = computed(() => (route.params.id ? Number(route.params.id) : null))
const canReply = computed(() => auth.can('inbox.reply'))
const totalUnread = computed(() => list.value.reduce((a, c) => a + c.unread, 0))
const thread = computed(() => withDays(messages.value))
const chanOptions = computed(() => [
  { value: '' as const, label: t('inbox.all') },
  { value: 'instagram' as const, label: 'Instagram' },
  { value: 'whatsapp' as const, label: 'WhatsApp' },
])
const ch = (c: Conversation) => (c.channel === 'instagram' ? 'ig' : 'wa')
const nameOf = (c: Conversation) => c.lead?.full_name ?? c.contact.name ?? (c.contact.username ? `@${c.contact.username}` : c.contact.phone ? formatPhone(c.contact.phone) : t('inbox.unknown'))
const stageLabel = (c: Conversation) => (c.lead?.stage_code && te(`crm.stage.${c.lead.stage_code}`) ? t(`crm.stage.${c.lead.stage_code}`) : c.lead?.stage ?? '')

async function loadList() {
  try {
    list.value = await inboxApi.list({ channel: channel.value, unread: unreadOnly.value, mine: mine.value, q: q.value.trim() || undefined })
  } catch {
    /* toast */
  } finally {
    listLoading.value = false
  }
}
let qTimer: ReturnType<typeof setTimeout> | undefined
watch(q, () => {
  clearTimeout(qTimer)
  qTimer = setTimeout(loadList, 300)
})
watch([channel, unreadOnly, mine], loadList)

async function openConv(cid: number | null) {
  conv.value = null
  messages.value = []
  text.value = ''
  if (!cid) return
  msgsLoading.value = true
  try {
    const [c, m] = await Promise.all([inboxApi.get(cid), inboxApi.messages(cid)])
    if (id.value !== cid) return
    conv.value = c
    messages.value = m
    hasMore.value = m.length >= 50
    const row = list.value.find((x) => x.id === cid)
    if (row) row.unread = 0
    counters.refresh()
    toBottom(true)
  } catch {
    router.replace('/inbox')
  } finally {
    msgsLoading.value = false
  }
}
watch(id, openConv)
onMounted(() => {
  loadList()
  openConv(id.value)
})

async function older() {
  const c = conv.value
  const first = messages.value[0]
  if (!c || !first) return
  const m = await inboxApi.messages(c.id, first.id).catch(() => [])
  hasMore.value = m.length >= 50
  keepPosition(() => (messages.value = [...m, ...messages.value]))
}

function pushMessage(m: InboxMessage) {
  if (messages.value.some((x) => x.id === m.id)) return
  messages.value = [...messages.value, m]
  toBottom(m.direction === 'out')
  const row = list.value.find((x) => x.id === conv.value?.id)
  if (row) {
    row.last_preview = m.text
    row.last_message_at = m.at
  }
}

async function send() {
  const c = conv.value
  const body = text.value.trim()
  if (!c || !body || sending.value) return
  sending.value = true
  try {
    pushMessage(await inboxApi.reply(c.id, body))
    text.value = ''
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) {
      c.in_window = false
      if (c.channel === 'whatsapp') tplOpen.value = true
      else toast.error(e.detail)
    } else toast.error(e instanceof ApiError && e.detail ? e.detail : t('errors.generic'))
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

async function toggleStatus() {
  const c = conv.value
  if (!c) return
  conv.value = await inboxApi.patch(c.id, { status: c.status === 'open' ? 'closed' : 'open' })
  loadList()
}

// Realtime: a new DM refreshes the list; the open thread pulls the new message.
let rtTimer: ReturnType<typeof setTimeout> | undefined
useRealtime('inbox.message', async (e) => {
  clearTimeout(rtTimer)
  rtTimer = setTimeout(loadList, 300)
  const c = conv.value
  if (c && e.conversation_id === c.id) {
    const last = messages.value[messages.value.length - 1]
    const fresh = await inboxApi.messages(c.id).catch(() => [])
    fresh.filter((m) => !last || m.id > last.id).forEach(pushMessage)
    c.in_window = true
  }
})
useRealtime('realtime.open', (e) => e.reconnect && (loadList(), conv.value && openConv(conv.value.id)))

const statusIcon = (m: InboxMessage) => (m.status === 'failed' ? t('inbox.failed') : m.status === 'read' ? t('inbox.read') : '')
</script>

<template>
  <div class="card inbox" :class="{ sel: id !== null }">
    <div class="ib-list">
      <div class="hd">
        <div class="ib-title">
          <h2 class="h-display">{{ t('nav.inbox') }}</h2>
          <span v-if="totalUnread" class="badge">{{ totalUnread }}</span>
          <span class="sp" />
          <button type="button" class="tgl sm" :aria-pressed="unreadOnly" @click="unreadOnly = !unreadOnly">{{ t('inbox.unread') }}</button>
          <button type="button" class="tgl sm" :aria-pressed="mine" @click="mine = !mine">{{ t('inbox.mine') }}</button>
        </div>
        <label class="search ib-search"><UiIcon name="search" :size="16" /><input v-model="q" type="search" :placeholder="t('inbox.searchPh')" :aria-label="t('top.search')" /></label>
        <UiSegmented v-model="channel" :options="chanOptions" :label="t('inbox.channel')" size="sm" block />
      </div>
      <div class="items" role="list">
        <template v-if="listLoading"><div v-for="i in 5" :key="i" class="dlg"><UiSkeleton circle width="40px" height="40px" /><div class="grow"><UiSkeleton :lines="2" /></div></div></template>
        <RouterLink v-for="c in list" v-else :key="c.id" :to="`/inbox/${c.id}`" class="dlg" :class="{ on: c.id === id, closed: c.status === 'closed' }" role="listitem">
          <UiAvatar :name="nameOf(c)" :channel="ch(c)" />
          <div class="grow">
            <div class="l1"><b>{{ nameOf(c) }}</b><time>{{ c.last_message_at ? relativeTime(c.last_message_at, loc) : '' }}</time></div>
            <div class="l2">
              <p>{{ c.last_preview ?? '' }}</p>
              <span v-if="c.lead?.stage_code === 'new'" class="chip info xs">{{ stageLabel(c) }}</span>
              <span v-if="c.unread" class="badge">{{ c.unread }}</span>
            </div>
          </div>
        </RouterLink>
        <UiEmptyState v-if="!listLoading && !list.length" icon="inbox" :title="t('inbox.empty')" />
      </div>
    </div>

    <div class="ib-chat">
      <template v-if="conv">
        <div class="hd">
          <UiButton class="back-btn" size="sm" variant="ghost" icon="arrow" :aria-label="t('common.back')" to="/inbox" />
          <UiAvatar :name="nameOf(conv)" :channel="ch(conv)" />
          <div class="grow">
            <b>{{ nameOf(conv) }}</b>
            <span>{{ conv.channel === 'instagram' ? 'Instagram Direct' : 'WhatsApp' }}<template v-if="conv.contact.username"> · @{{ conv.contact.username }}</template><template v-if="conv.contact.phone"> · {{ formatPhone(conv.contact.phone) }}</template></span>
          </div>
          <span v-if="conv.lead" class="chip info hd-stage">{{ stageLabel(conv) }}</span>
          <UiButton v-if="conv.lead && auth.can('crm.view')" class="hd-cta" size="sm" variant="primary" icon="crm" :to="{ path: '/crm', query: { lead: conv.lead.id } }"><span class="cta-t">{{ t('inbox.openLead') }}</span></UiButton>
          <UiButton v-if="canReply" size="sm" variant="ghost" :icon="conv.status === 'open' ? 'archive' : 'inbox'" :title="conv.status === 'open' ? t('inbox.close') : t('inbox.reopen')" :aria-label="conv.status === 'open' ? t('inbox.close') : t('inbox.reopen')" @click="toggleStatus" />
        </div>
        <div ref="msgsEl" class="msgs" aria-live="polite" @scroll="onScroll">
          <button v-if="hasMore" type="button" class="day more-btn" @click="older">{{ t('chats.older') }}</button>
          <template v-for="m in thread" :key="m.id">
            <span v-if="m.newDay" class="day">{{ dayTitle(m.at, loc, t('chats.today'), t('chats.yesterday')) }}</span>
            <div class="b" :class="[m.direction, { failed: m.status === 'failed', tpl: m.kind === 'template' }]">
              <span v-if="m.kind === 'template'" class="by"><UiIcon name="zap" :size="14" /> {{ t('inbox.template') }}</span>
              <img v-if="m.media_url && m.kind === 'image'" :src="m.media_url" alt="" class="photo" loading="lazy" />
              <a v-else-if="m.media_url" :href="m.media_url" target="_blank" rel="noopener" class="file"><span class="fi">{{ m.kind.toUpperCase().slice(0, 3) }}</span>{{ t('chats.file') }}</a>
              <span class="pre">{{ m.text }}</span>
              <time>{{ hm(m.at, loc) }}<template v-if="statusIcon(m)"> · {{ statusIcon(m) }}</template></time>
            </div>
          </template>
          <div v-if="!messages.length && !msgsLoading" class="sys"><UiIcon name="chat" :size="18" /><div>{{ t('inbox.noMessages') }}</div></div>
        </div>
        <div v-if="canReply" class="composer">
          <div v-if="!conv.in_window" class="window closed">
            <UiIcon name="clock" :size="16" />
            <span class="grow">{{ conv.channel === 'whatsapp' ? t('inbox.windowClosed') : t('inbox.windowClosedIg') }}</span>
            <UiButton v-if="conv.channel === 'whatsapp'" size="sm" variant="navy" icon="zap" @click="tplOpen = true">{{ t('inbox.sendTpl') }}</UiButton>
          </div>
          <div class="cin">
            <textarea v-model="text" rows="1" :placeholder="conv.channel === 'instagram' ? t('inbox.replyIg') : t('inbox.replyWa')" :aria-label="t('chats.message')" :disabled="!conv.in_window && conv.channel === 'instagram'" @keydown="onKey" />
            <button type="button" class="send" :aria-label="t('chats.send')" :disabled="!text.trim() || sending" @click="send"><UiIcon name="send" /></button>
          </div>
          <div v-if="conv.in_window" class="window"><UiIcon name="clock" :size="16" />{{ t('inbox.windowOpen') }}</div>
        </div>
        <div v-else class="composer"><div class="window"><UiIcon name="lock" :size="16" />{{ t('inbox.readOnly') }}</div></div>
      </template>
      <div v-else-if="msgsLoading" class="msgs"><UiSkeleton :lines="5" /></div>
      <UiEmptyState v-else large icon="inbox" :title="t('inbox.pick')" :text="t('inbox.pickText')" />
    </div>

    <aside v-if="conv" class="ib-lead">
      <div style="display: flex; gap: 12px; align-items: center">
        <UiAvatar :name="nameOf(conv)" size="lg" />
        <div><b style="font-size: 15px">{{ nameOf(conv) }}</b><div v-if="conv.lead" class="muted" style="font-size: 12.5px">{{ t('crm.leadN', { n: conv.lead.id }) }}</div></div>
      </div>
      <div style="display: grid; gap: 8px; margin-top: 14px">
        <UiButton v-if="conv.lead && auth.can('crm.view')" variant="primary" block icon="crm" :to="{ path: '/crm', query: { lead: conv.lead.id } }">{{ t('inbox.openLead') }}</UiButton>
        <UiButton v-if="conv.contact.student_id && auth.can('students.view')" block icon="user" :to="{ name: 'student', params: { id: conv.contact.student_id } }">{{ t('crm.openStudent') }}</UiButton>
      </div>
      <h4>{{ t('crm.data') }}</h4>
      <dl class="kv">
        <dt>{{ t('crm.sourceLabel') }}</dt>
        <dd style="display: flex; gap: 6px; align-items: center"><span class="srcico" :class="ch(conv)" style="width: 18px; height: 18px"><svg style="width: 12px; height: 12px"><use :href="`#i-${ch(conv)}`" /></svg></span>{{ conv.channel === 'instagram' ? 'Instagram' : 'WhatsApp' }}</dd>
        <template v-if="conv.contact.phone"><dt>{{ t('students.form.phone') }}</dt><dd>{{ formatPhone(conv.contact.phone) }}</dd></template>
        <template v-if="conv.lead"><dt>{{ t('crm.stageLabel') }}</dt><dd>{{ stageLabel(conv) }}</dd></template>
        <dt>{{ t('branch.label') }}</dt><dd>{{ conv.branch_id ? refs.branchName(conv.branch_id) : '—' }}</dd>
        <dt>{{ t('students.col.status') }}</dt><dd><UiChip :tone="conv.status === 'open' ? 'ok' : undefined" small>{{ t(`inbox.status.${conv.status}`) }}</UiChip></dd>
      </dl>
    </aside>
  </div>
  <TemplateModal v-model:open="tplOpen" :conversation="conv" @sent="pushMessage" />
</template>
