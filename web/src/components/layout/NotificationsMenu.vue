<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import UiIcon from '@/components/ui/UiIcon.vue'
import UiEmptyState from '@/components/ui/UiEmptyState.vue'
import { useClickOutside } from '@/composables/useClickOutside'

/** Shape of a notification once the backend sends them. */
interface Notice {
  id: number
  icon: string
  tone: 'ig' | 'wa' | 'qr' | 'red' | 'warn'
  title: string
  text: string
  meta: string
}

const { t } = useI18n()
const open = ref(false)
const root = ref<HTMLElement | null>(null)
const items = ref<Notice[]>([])
useClickOutside([root], () => (open.value = false))
</script>

<template>
  <div ref="root" class="top-pop">
    <button
      type="button"
      class="iconbtn"
      :aria-label="t('top.notifications')"
      :aria-expanded="open"
      aria-haspopup="true"
      @click="open = !open"
    >
      <UiIcon name="bell" /><span v-if="items.length" class="dot" />
    </button>
    <Transition name="pop">
      <div v-if="open" class="notif" role="dialog" :aria-label="t('top.notifications')">
        <div class="nh">{{ t('top.notifications') }}</div>
        <div v-for="n in items" :key="n.id" class="it">
          <span class="srcico" :class="n.tone"><svg aria-hidden="true"><use :href="`#i-${n.icon}`" /></svg></span>
          <div><p><b>{{ n.title }}</b> — {{ n.text }}</p><span>{{ n.meta }}</span></div>
        </div>
        <UiEmptyState v-if="!items.length" icon="bell" :title="t('top.noNotifications')" :text="t('top.noNotificationsHint')" />
      </div>
    </Transition>
  </div>
</template>
