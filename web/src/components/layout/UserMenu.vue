<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import UiAvatar from '@/components/ui/UiAvatar.vue'
import UiChip from '@/components/ui/UiChip.vue'
import UiIcon from '@/components/ui/UiIcon.vue'
import UiSegmented from '@/components/ui/UiSegmented.vue'
import ThemePicker from '@/components/layout/ThemePicker.vue'
import { useClickOutside } from '@/composables/useClickOutside'
import { authApi } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import { useBranchStore } from '@/stores/branch'
import { useUiStore } from '@/stores/ui'
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
  if (u.active_role) return te(`roles.${u.active_role}`) ? t(`roles.${u.active_role}`) : (u.all_roles?.find((r) => r.code === u.active_role)?.name ?? u.active_role)
  return u.position || (te(`roles.${code}`) ? t(`roles.${code}`) : code)
})
const branchLabel = computed(() => (branch.current.id === null ? t('branch.all') : branch.current.name))
const subtitle = computed(() => (auth.isStaff && branchLabel.value ? `${roleName.value} · ${branchLabel.value}` : roleName.value))

const langs = computed<{ value: Locale; label: string }[]>(() => [
  { value: 'ru', label: t('lang.ru') },
  { value: 'kk', label: t('lang.kk') },
])

/** «Работать как»: with several roles the person picks one, the menu and accesses follow it. */
const myRoles = computed(() => user.value?.all_roles ?? [])
const roleLabel = (r: { code: string; name: string }) => (te(`roles.${r.code}`) ? t(`roles.${r.code}`) : r.name)
const switching = ref(false)
async function workAs(code: string | null) {
  if (switching.value || (user.value?.active_role ?? null) === code) return
  switching.value = true
  try {
    await authApi.setActiveRole(code)
    window.location.assign('/')
  } catch {
    switching.value = false
  }
}

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
        <template v-if="auth.isStaff">
          <button type="button" class="mi" role="menuitem" @click="go(`/staff/${user.id}`)"><UiIcon name="user" :size="18" />{{ t('nv.profile.mine') }}</button>
          <button v-if="auth.can('payroll.view')" type="button" class="mi" role="menuitem" @click="go('/payroll?tab=my')"><UiIcon name="salary" :size="18" />{{ t('user.myPay') }}</button>
          <button type="button" class="mi" role="menuitem" @click="go('/feedback')"><UiIcon name="flag" :size="18" />{{ t('user.feedback') }}</button>
          <button type="button" class="mi" role="menuitem" @click="go('/rules')"><UiIcon name="file" :size="18" />{{ t('user.rules') }}</button>
        </template>
        <template v-if="auth.isStaff && myRoles.length > 1">
          <hr />
          <div class="hd2">{{ t('nv.workAs.title') }}</div>
          <button type="button" class="mi" role="menuitemradio" :aria-checked="!user.active_role" :disabled="switching" @click="workAs(null)">
            <UiIcon :name="!user.active_role ? 'check' : 'users'" :size="18" />{{ t('nv.workAs.all') }}
          </button>
          <button v-for="r in myRoles" :key="r.code" type="button" class="mi" role="menuitemradio" :aria-checked="user.active_role === r.code" :disabled="switching" @click="workAs(r.code)">
            <UiIcon :name="user.active_role === r.code ? 'check' : 'user'" :size="18" />{{ roleLabel(r) }}
          </button>
        </template>
        <hr />
        <div class="row stack-row"><span>{{ t('user.theme') }} · {{ t(`theme.${ui.theme}`) }}</span><ThemePicker compact /></div>
        <div class="row"><span>{{ t('user.language') }}</span><UiSegmented v-model="ui.locale" :options="langs" :label="t('user.language')" size="sm" /></div>
        <hr />
        <button type="button" class="mi danger" role="menuitem" @click="logout"><UiIcon name="logout" :size="18" />{{ t('user.logout') }}</button>
      </div>
    </Transition>
  </div>
</template>
