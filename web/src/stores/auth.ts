import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { authApi, type Me, type Scope, type TokenOut } from '@/api/auth'
import { hasAccessToken, refreshAccess, setAccessToken } from '@/api/http'
import { readPref, writePref } from '@/utils/storage'
import { stopRealtime } from '@/composables/useRealtime'
import { useRefsStore } from './refs'
import { usePortalStore } from './portal'

export type LoginStep =
  | { step: 'done' }
  | { step: 'mfa'; mfaToken: string }
  | { step: 'setup' }

const RANK: Record<Scope, number> = { own: 0, branch: 1, network: 2 }
/**
 * A non-secret hint that this browser has signed in before, so a first-time visitor
 * doesn't fire a refresh that can only fail with 401. The session itself is the httpOnly cookie.
 */
const HINT = 'oe-signed-in'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<Me | null>(null)
  /** True once the boot-time session restore has finished (with or without a user). */
  const ready = ref(false)
  let booting: Promise<void> | null = null

  const isAuthenticated = computed(() => user.value !== null)
  const isStaff = computed(() => user.value?.kind === 'staff')
  /** Staff must enable 2FA before using the app; the server decides (`require_staff_2fa`). */
  const mfaSetupRequired = computed(() => {
    const u = user.value
    if (!u) return false
    return u.mfa_setup_required ?? (u.kind === 'staff' && !u.totp_enabled)
  })
  const hasNetworkScope = computed(() =>
    Object.values(user.value?.permissions ?? {}).some((s) => s === 'network'),
  )

  /**
   * Does the user hold `module.action`? With `scope`, the grant must be at least that wide.
   * UI hint only: the backend enforces every permission.
   */
  function can(key: string, scope?: Scope): boolean {
    const granted = user.value?.permissions[key]
    if (!granted) return false
    return scope ? RANK[granted] >= RANK[scope] : true
  }

  /** Any action in the module. */
  function canAny(module: string): boolean {
    const prefix = `${module}.`
    return Object.keys(user.value?.permissions ?? {}).some((k) => k.startsWith(prefix))
  }

  async function fetchMe(): Promise<Me | null> {
    try {
      user.value = await authApi.me()
    } catch {
      user.value = null
    }
    return user.value
  }

  /** Restore the session from the refresh cookie on first load. Safe to call many times. */
  function init(): Promise<void> {
    if (!booting) {
      booting = (async () => {
        if (hasAccessToken() || (readPref(HINT) && (await refreshAccess()))) await fetchMe()
        if (!user.value) writePref(HINT, null)
        ready.value = true
      })()
    }
    return booting
  }

  async function acceptTokens(out: TokenOut): Promise<LoginStep> {
    if (out.mfa_required && out.mfa_token) return { step: 'mfa', mfaToken: out.mfa_token }
    setAccessToken(out.access_token)
    writePref(HINT, '1')
    await fetchMe()
    return out.mfa_setup_required || mfaSetupRequired.value ? { step: 'setup' } : { step: 'done' }
  }

  async function login(phone: string, password: string): Promise<LoginStep> {
    return acceptTokens(await authApi.login(phone, password))
  }

  async function verifyMfa(mfaToken: string, code: string): Promise<LoginStep> {
    return acceptTokens(await authApi.mfa(mfaToken, code))
  }

  async function verifyOtp(phone: string, code: string): Promise<LoginStep> {
    return acceptTokens(await authApi.otpVerify(phone, code))
  }

  async function enableTotp(code: string): Promise<void> {
    const out = await authApi.totpEnable(code)
    setAccessToken(out.access_token)
    await fetchMe()
  }

  /** Forget the session locally (server already ended it, or refresh failed). */
  function clear() {
    stopRealtime()
    useRefsStore().reset()
    usePortalStore().reset()
    setAccessToken(null)
    user.value = null
    writePref(HINT, null)
  }

  async function logout() {
    try {
      if (user.value) await authApi.logout()
    } catch {
      /* the session is gone either way */
    }
    clear()
  }

  return {
    user, ready, isAuthenticated, isStaff, mfaSetupRequired, hasNetworkScope,
    can, canAny, init, fetchMe, login, verifyMfa, verifyOtp, enableTotp, logout, clear,
  }
})

