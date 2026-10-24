<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import UiAvatar from '@/components/ui/UiAvatar.vue'
import UiChip from '@/components/ui/UiChip.vue'
import UiIcon from '@/components/ui/UiIcon.vue'
import UiSegmented from '@/components/ui/UiSegmented.vue'
import { useClickOutside } from '@/composables/useClickOutside'
import { useAuthStore } from '@/stores/auth'
import { useBranchStore } from '@/stores/branch'
import { useUiStore, type ThemePref } from '@/stores/ui'
import type { Locale } from '@/i18n'

const auth = useAuthStore()
const ui = useUiStore()
const branch = useBranchStore()
const router = useRouter()
const { t, te } = useI18n()

const open = ref(false)
const root = ref<HTMLElement | null>(null)
useClickOutside([root], () => (open.value = false))

const user = computed(() => auth.user)
const roleName = computed(() => {
  const u = user.value
  if (!u) return ''
  const code = u.roles[0] ?? u.kind
  return u.position || (te(`roles.${code}`) ? t(`roles.${code}`) : code)
})
const subtitle = computed(() => (auth.isStaff ? `${roleName.value} · ${t(`branch.${branch.current.key}`)}` : roleName.value))

const themes = computed<{ value: ThemePref; label: string; icon: string; iconOnly: boolean }[]>(() => [
  { value: 'light', label: t('theme.light'), icon: 'sun', iconOnly: true },
  { value: 'dark', label: t('theme.dark'), icon: 'moon', iconOnly: true },
  { value: 'system', label: t('theme.system'), icon: 'laptop', iconOnly: true },
])
const langs = computed<{ value: Locale; label: string }[]>(() => [
  { value: 'ru', label: t('lang.ru') },
  { value: 'kk', label: t('lang.kk') },
])

function go(path: string) {
  open.value = false
  router.push(path)
}

async function logout() {
  open.value = false
  await auth.logout()
  router.replace({ name: 'login' })
}
</script>

<template>
  <div v-if="user" ref="root" class="top-pop">
    <button type="button" class="me" :aria-expanded="open" aria-haspopup="menu" :aria-label="t('top.userMenu')" @click="open = !open">
      <UiAvatar :name="user.full_name" :src="user.avatar_url" :color="(user.id % 8) + 1" />
      <span class="who"><b>{{ user.full_name }}</b><span>{{ subtitle }}</span></span>
      <UiIcon name="down" :size="16" class="muted chev" />
    </button>
    <Transition name="pop">
      <div v-if="open" class="menu" role="menu">
        <div class="hd2">{{ user.full_name }} · {{ roleName }}</div>
        <button type="button" class="mi" role="menuitem" @click="go('/settings/security')">
          <UiIcon name="shield" :size="18" />{{ t('user.security') }}
          <UiChip v-if="auth.isStaff" :tone="user.totp_enabled ? 'ok' : 'warn'" small>{{ user.totp_enabled ? t('user.twoFaOn') : t('user.twoFaOff') }}</UiChip>
        </button>
        <button type="button" class="mi" role="menuitem" @click="go('/settings/security#sessions')">
          <UiIcon name="laptop" :size="18" />{{ t('user.sessions') }}
        </button>
        <hr />
        <div class="row"><span>{{ t('user.theme') }}</span><UiSegmented v-model="ui.theme" :options="themes" :label="t('user.theme')" size="sm" /></div>
        <div class="row"><span>{{ t('user.language') }}</span><UiSegmented v-model="ui.locale" :options="langs" :label="t('user.language')" size="sm" /></div>
        <hr />
        <button type="button" class="mi danger" role="menuitem" @click="logout"><UiIcon name="logout" :size="18" />{{ t('user.logout') }}</button>
      </div>
    </Transition>
  </div>
</template>
