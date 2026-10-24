<script setup lang="ts">
import { useSourceLabel } from '@/composables/useSourceLabel'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import UiIcon from '@/components/ui/UiIcon.vue'
import UiKbd from '@/components/ui/UiKbd.vue'
import UiModal from '@/components/ui/UiModal.vue'
import UiInput from '@/components/ui/UiInput.vue'
import UiEmptyState from '@/components/ui/UiEmptyState.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { useHotkey } from '@/composables/useHotkey'
import { useMediaQuery } from '@/composables/useMediaQuery'
import { useClickOutside } from '@/composables/useClickOutside'
import { chatsApi, searchApi, type SearchOut } from '@/api/chats'
import { useAuthStore } from '@/stores/auth'
import { useRefsStore } from '@/stores/refs'

interface Hit {
  key: string
  kind: 'students' | 'leads' | 'groups' | 'staff'
  id: number
  title: string
  sub: string
}

const { t } = useI18n()
const srcLabel = useSourceLabel()
const router = useRouter()
const auth = useAuthStore()
const refs = useRefsStore()
const query = ref('')
const input = ref<HTMLInputElement | null>(null)
const box = ref<HTMLElement | null>(null)
const modalOpen = ref(false)
const popOpen = ref(false)
const narrow = useMediaQuery('(max-width: 760px)')
const isMac = /Mac|iPhone|iPad/.test(navigator.platform)
const result = ref<SearchOut | null>(null)
const loading = ref(false)
const active = ref(0)
let ctrl: AbortController | null = null
let timer: ReturnType<typeof setTimeout> | undefined

const ICONS = { students: 'users', leads: 'crm', groups: 'groups', staff: 'user' } as const
const hits = computed<Hit[]>(() => {
  const r = result.value
  if (!r) return []
  const out: Hit[] = []
  for (const kind of ['students', 'leads', 'groups', 'staff'] as const) {
    for (const h of r[kind] ?? []) {
      const sub =
        kind === 'students' ? [h.status ? t(`students.status.${h.status}`) : '', refs.branchName(h.branch_id)].filter(Boolean).join(' · ')
        : kind === 'leads' ? [srcLabel(h.source), refs.branchName(h.branch_id)].filter(Boolean).join(' · ')
        : kind === 'groups' ? refs.branchName(h.branch_id)
        : h.position ?? t('roles.staff')
      out.push({ key: `${kind}${h.id}`, kind, id: h.id, title: h.title, sub })
    }
  }
  return out
})
const sections = computed(() => (['students', 'leads', 'groups', 'staff'] as const)
  .map((kind) => ({ kind, items: hits.value.filter((h) => h.kind === kind) }))
  .filter((s) => s.items.length))

watch(query, (q) => {
  clearTimeout(timer)
  active.value = 0
  if (q.trim().length < 2) {
    ctrl?.abort()
    result.value = null
    loading.value = false
    return
  }
  loading.value = true
  timer = setTimeout(async () => {
    ctrl?.abort()
    ctrl = new AbortController()
    try {
      result.value = await searchApi.search(q.trim(), ctrl.signal)
      loading.value = false
    } catch (e) {
      if (!(e instanceof DOMException)) {
        result.value = {}
        loading.value = false
      }
    }
  }, 220)
})

function focusSearch() {
  if (narrow.value) modalOpen.value = true
  else {
    input.value?.focus()
    input.value?.select()
    popOpen.value = true
  }
}
useHotkey('k', focusSearch)
useClickOutside([box], () => (popOpen.value = false))

async function go(h: Hit) {
  popOpen.value = modalOpen.value = false
  query.value = ''
  input.value?.blur()
  if (h.kind === 'students') router.push({ name: 'student', params: { id: h.id } })
  else if (h.kind === 'groups') router.push(`/groups/${h.id}`)
  else if (h.kind === 'leads') router.push({ path: '/crm', query: { lead: h.id } })
  else if (auth.can('chats.use')) {
    try {
      const chat = await chatsApi.direct(h.id)
      router.push(`/chats/${chat.id}`)
    } catch {
      /* reason shown as a toast */
    }
  }
}

function onKey(e: KeyboardEvent) {
  const n = hits.value.length
  if (e.key === 'ArrowDown' && n) {
    e.preventDefault()
    active.value = (active.value + 1) % n
  } else if (e.key === 'ArrowUp' && n) {
    e.preventDefault()
    active.value = (active.value - 1 + n) % n
  } else if (e.key === 'Enter') {
    const h = hits.value[active.value]
    if (h) {
      e.preventDefault()
      go(h)
    }
  } else if (e.key === 'Escape') {
    popOpen.value = false
    input.value?.blur()
  }
}
const showPop = computed(() => popOpen.value && query.value.trim().length >= 2 && !narrow.value)
</script>

<template>
  <div ref="box" class="search-wrap top-pop">
    <label class="search">
      <UiIcon name="search" :size="18" />
      <input
        ref="input" v-model="query" type="search" :placeholder="t('top.searchPlaceholder')" :aria-label="t('top.search')"
        role="combobox" :aria-expanded="showPop" aria-controls="search-results" autocomplete="off"
        @focus="popOpen = true" @keydown="onKey"
      />
      <UiKbd>{{ isMac ? '⌘' : 'Ctrl' }} K</UiKbd>
    </label>
    <Transition name="pop">
      <div v-if="showPop" id="search-results" class="menu search-pop" role="listbox">
        <template v-if="loading && !result"><div v-for="i in 3" :key="i" class="sr-sk"><UiSkeleton width="70%" /></div></template>
        <template v-else-if="hits.length">
          <template v-for="s in sections" :key="s.kind">
            <div class="hd2">{{ t(`search.${s.kind}`) }}</div>
            <button
              v-for="h in s.items" :key="h.key" type="button" class="mi sr-it" role="option"
              :aria-selected="hits[active]?.key === h.key" :class="{ act: hits[active]?.key === h.key }"
              @mouseenter="active = hits.indexOf(h)" @click="go(h)"
            >
              <UiIcon :name="ICONS[h.kind]" :size="18" /><span class="grow"><b>{{ h.title }}</b><small>{{ h.sub }}</small></span>
            </button>
          </template>
        </template>
        <p v-else class="muted sr-empty">{{ t('common.nothingFound') }}</p>
      </div>
    </Transition>
  </div>
  <button type="button" class="iconbtn search-btn" :aria-label="t('top.search')" @click="modalOpen = true">
    <UiIcon name="search" />
  </button>
  <UiModal v-model:open="modalOpen" :title="t('top.search')">
    <div class="stack" @keydown="onKey">
      <UiInput v-model="query" type="search" icon="search" :placeholder="t('top.searchPlaceholder')" autofocus />
      <div v-if="hits.length" class="sr-list">
        <template v-for="s in sections" :key="s.kind">
          <div class="hd2">{{ t(`search.${s.kind}`) }}</div>
          <button v-for="h in s.items" :key="h.key" type="button" class="mi sr-it" :class="{ act: hits[active]?.key === h.key }" @click="go(h)">
            <UiIcon :name="ICONS[h.kind]" :size="18" /><span class="grow"><b>{{ h.title }}</b><small>{{ h.sub }}</small></span>
          </button>
        </template>
      </div>
      <UiEmptyState v-else icon="search" :title="query.trim().length >= 2 && !loading ? t('common.nothingFound') : t('top.search')" :text="query.trim().length < 2 ? t('top.searchHint') : undefined" />
    </div>
  </UiModal>
</template>
