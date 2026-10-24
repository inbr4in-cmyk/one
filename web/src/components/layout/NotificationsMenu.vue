<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import UiIcon from '@/components/ui/UiIcon.vue'
import UiEmptyState from '@/components/ui/UiEmptyState.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { useClickOutside } from '@/composables/useClickOutside'
import { notifyApi, type Notice } from '@/api/chats'
import { useCountersStore } from '@/stores/counters'
import { useUiStore } from '@/stores/ui'
import { relativeTime } from '@/utils/format'

const { t } = useI18n()
const router = useRouter()
const counters = useCountersStore()
const ui = useUiStore()
const open = ref(false)
const root = ref<HTMLElement | null>(null)
const items = ref<Notice[] | null>(null)
useClickOutside([root], () => (open.value = false))

const unread = computed(() => counters.counts.notifications)
const KIND_ICON: Record<string, { icon: string; tone: string }> = {
  inbox: { icon: 'inbox', tone: 'web' },
  lead: { icon: 'crm', tone: 'qr' },
  chat: { icon: 'chat', tone: 'web' },
  attendance: { icon: 'check', tone: 'ref' },
  payment: { icon: 'wallet', tone: 'wa' },
  task: { icon: 'task', tone: 'ref' },
}
const look = (kind: string) => KIND_ICON[kind] ?? { icon: 'bell', tone: 'qr' }

async function toggle() {
  open.value = !open.value
  if (open.value) {
    try {
      items.value = (await notifyApi.list()).items
    } catch {
      items.value = []
    }
  }
}

async function readAll() {
  await notifyApi.readAll().catch(() => {})
  items.value = items.value?.map((n) => ({ ...n, read: true })) ?? null
  counters.refresh()
}

function go(n: Notice) {
  open.value = false
  if (n.link?.startsWith('/')) router.push(n.link)
}
</script>

<template>
  <div ref="root" class="top-pop">
    <button
      type="button"
      class="iconbtn"
      :aria-label="unread ? `${t('top.notifications')}: ${unread}` : t('top.notifications')"
      :aria-expanded="open"
      aria-haspopup="true"
      @click="toggle"
    >
      <UiIcon name="bell" /><span v-if="unread" class="dot" />
    </button>
    <Transition name="pop">
      <div v-if="open" class="notif" role="dialog" :aria-label="t('top.notifications')">
        <div class="nh">
          {{ t('top.notifications') }}<span class="sp" />
          <button v-if="items?.some((n) => !n.read)" type="button" class="btn sm ghost" @click="readAll">{{ t('top.readAll') }}</button>
        </div>
        <div class="notif-list">
          <template v-if="items === null">
            <div v-for="i in 3" :key="i" class="it"><UiSkeleton width="22px" height="22px" /><div class="grow"><UiSkeleton :lines="2" /></div></div>
          </template>
          <button v-for="n in items ?? []" :key="n.id" type="button" class="it" :class="{ unread: !n.read }" @click="go(n)">
            <span class="srcico" :class="look(n.kind).tone"><svg aria-hidden="true"><use :href="`#i-${look(n.kind).icon}`" /></svg></span>
            <div class="grow"><p><b>{{ n.title }}</b><template v-if="n.body"> — {{ n.body }}</template></p><span>{{ relativeTime(n.at, ui.locale) }}</span></div>
          </button>
          <UiEmptyState v-if="items && !items.length" icon="bell" :title="t('top.noNotifications')" :text="t('top.noNotificationsHint')" />
        </div>
      </div>
    </Transition>
  </div>
</template>
