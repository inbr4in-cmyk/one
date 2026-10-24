<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import UiButton from '@/components/ui/UiButton.vue'
import UiCard from '@/components/ui/UiCard.vue'
import UiChip from '@/components/ui/UiChip.vue'
import UiEmptyState from '@/components/ui/UiEmptyState.vue'
import UiIcon from '@/components/ui/UiIcon.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { authApi, type SessionOut } from '@/api/auth'
import { useToastStore } from '@/stores/toast'
import { useUiStore } from '@/stores/ui'
import { describeUserAgent, relativeTime } from '@/utils/format'

const { t } = useI18n()
const toast = useToastStore()
const ui = useUiStore()

const sessions = ref<SessionOut[] | null>(null)
const failed = ref(false)
const ending = ref<Set<number>>(new Set())
const endingAll = ref(false)

const others = computed(() => sessions.value?.filter((s) => !s.current) ?? [])

async function load() {
  failed.value = false
  try {
    sessions.value = await authApi.sessions()
  } catch {
    failed.value = true
  }
}

async function end(id: number) {
  ending.value = new Set(ending.value).add(id)
  try {
    await authApi.endSession(id)
    sessions.value = sessions.value?.filter((s) => s.id !== id) ?? null
    toast.ok(t('security.sessionEnded'))
  } catch {
    /* toast shown by the API client */
  } finally {
    const next = new Set(ending.value)
    next.delete(id)
    ending.value = next
  }
}

async function endOthers() {
  endingAll.value = true
  try {
    await authApi.endOtherSessions()
    sessions.value = sessions.value?.filter((s) => s.current) ?? null
    toast.ok(t('security.sessionsEnded'))
  } catch {
    /* toast shown by the API client */
  } finally {
    endingAll.value = false
  }
}

function view(s: SessionOut) {
  const dev = describeUserAgent(s.user_agent)
  return {
    title: dev?.label ?? t('security.unknownDevice'),
    icon: dev?.mobile ? 'mobile' : 'laptop',
    meta: [s.ip, relativeTime(s.last_used_at, ui.locale)].filter(Boolean).join(' · '),
  }
}

defineExpose({ reload: load })
onMounted(load)
</script>

<template>
  <UiCard id="sessions" icon="laptop" :title="t('security.sessions')">
    <template #actions>
      <UiButton v-if="others.length" size="sm" :loading="endingAll" @click="endOthers">{{ t('security.endOthers') }}</UiButton>
    </template>
    <div v-if="failed">
      <UiEmptyState icon="alert" :title="t('errors.generic')">
        <UiButton size="sm" @click="load">{{ t('common.retry') }}</UiButton>
      </UiEmptyState>
    </div>
    <div v-else-if="!sessions">
      <div v-for="i in 3" :key="i" class="sess">
        <UiSkeleton width="36px" height="36px" />
        <div class="grow"><UiSkeleton :lines="2" /></div>
      </div>
    </div>
    <TransitionGroup v-else tag="div" name="fade" class="stagger">
      <div v-for="s in sessions" :key="s.id" class="sess">
        <span class="dv"><UiIcon :name="view(s).icon" :size="18" /></span>
        <div class="grow">
          <b>
            {{ view(s).title }}
            <UiChip v-if="s.current" tone="ok" small>{{ t('security.current') }}</UiChip>
            <UiChip v-if="!s.mfa_passed" tone="warn" small>{{ t('security.noMfa') }}</UiChip>
          </b>
          <span class="meta">{{ view(s).meta }}</span>
        </div>
        <UiButton v-if="!s.current" size="sm" :loading="ending.has(s.id)" @click="end(s.id)">{{ t('security.end') }}</UiButton>
      </div>
    </TransitionGroup>
    <p v-if="sessions && !others.length" class="card-note">{{ t('security.noSessions') }}</p>
  </UiCard>
</template>
