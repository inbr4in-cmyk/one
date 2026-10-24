import { http } from './http'

/** Contracts from backend/app/modules/auth/router.py */
export interface TokenOut {
  access_token: string | null
  refresh_token: string | null
  token_type: string
  mfa_required: boolean
  mfa_token: string | null
  mfa_setup_required: boolean
}

export type Scope = 'own' | 'branch' | 'network'
export type UserKind = 'staff' | 'student' | 'parent'

export interface Me {
  id: number
  kind: UserKind
  full_name: string
  phone: string
  locale: string
  avatar_url: string | null
  position: string | null
  totp_enabled: boolean
  mfa: boolean
  roles: string[]
  branch_ids: number[]
  permissions: Record<string, Scope>
  rules_accepted_version: string | null
}

export interface SessionOut {
  id: number
  user_agent: string | null
  ip: string | null
  created_at: string
  last_used_at: string
  mfa_passed: boolean
  current: boolean
}

export interface TotpSetup {
  secret: string
  uri: string
}

const anon = { auth: false } as const

export const authApi = {
  login: (phone: string, password: string) => http.post<TokenOut>('/auth/login', { phone, password }, anon),
  mfa: (mfa_token: string, code: string) => http.post<TokenOut>('/auth/mfa', { mfa_token, code }, anon),
  otpRequest: (phone: string) => http.post<null>('/auth/otp/request', { phone }, anon),
  otpVerify: (phone: string, code: string) => http.post<TokenOut>('/auth/otp/verify', { phone, code }, anon),
  me: () => http.get<Me>('/auth/me', { silent: true }),
  logout: () => http.post<null>('/auth/logout', undefined, { silent: true }),
  totpSetup: () => http.post<TotpSetup>('/auth/2fa/setup'),
  totpEnable: (code: string) => http.post<TokenOut>('/auth/2fa/enable', { code }),
  changePassword: (old_password: string, new_password: string) =>
    http.post<null>('/auth/password', { old_password, new_password }),
  sessions: () => http.get<SessionOut[]>('/auth/sessions'),
  endSession: (id: number) => http.delete(`/auth/sessions/${id}`),
}
