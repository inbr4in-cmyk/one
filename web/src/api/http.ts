/**
 * HTTP client for the One English API.
 *
 * - Base path `/api` (Vite proxies it to the backend in dev).
 * - The access token lives in memory only. The refresh token is an httpOnly cookie
 *   scoped to /api/auth that this code never sees.
 * - On 401 we refresh once and retry; concurrent requests share a single refresh.
 * - Errors are surfaced through a handler (toasts) with the server's `detail`.
 */

const BASE = '/api'

/**
 * Offline demo build only (`npm run build:demo`): src/demo/entry.ts installs these hooks before the app
 * starts and requests are answered in the browser from fixtures. The regular build never has them.
 */
export interface DemoHooks {
  request: (method: string, path: string, opts: RequestOptions) => Promise<unknown>
  restore: () => Promise<boolean>
  download: () => void
}
const demo = (): DemoHooks | undefined =>
  import.meta.env.VITE_DEMO === '1' ? (globalThis as { __oeDemo?: DemoHooks }).__oeDemo : undefined
const CSRF_HEADER = { 'X-Requested-With': 'one-english' }

let accessToken: string | null = null
let refreshing: Promise<boolean> | null = null

type Handler<T> = ((arg: T) => void) | null
let onAuthLost: Handler<void> = null
let onError: Handler<ApiError> = null
let onMfaRequired: Handler<void> = null

export class ApiError extends Error {
  readonly status: number
  readonly detail: string
  /** Seconds from a 429's Retry-After header, when the server sent one. */
  readonly retryAfter: number | null
  constructor(status: number, detail: string, retryAfter: number | null = null) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
    this.retryAfter = retryAfter
  }
}

export interface RequestOptions {
  body?: unknown
  /** Send the bearer token and refresh on 401. Default true. */
  auth?: boolean
  /** Do not show an error toast; the caller handles the error. */
  silent?: boolean
  signal?: AbortSignal
  /** Extra request headers (e.g. Idempotency-Key). */
  headers?: Record<string, string>
}

export function setAccessToken(token: string | null): void {
  accessToken = token
}

export function hasAccessToken(): boolean {
  return accessToken !== null
}

/** Called when the session cannot be restored (refresh failed). */
export function setAuthLostHandler(fn: () => void): void {
  onAuthLost = fn
}

/** Called when the server refuses a staff endpoint until 2FA is set up (REQUIRE_STAFF_2FA). */
export function setMfaRequiredHandler(fn: () => void): void {
  onMfaRequired = fn
}

/** Called for every failed request that is not `silent`. */
export function setErrorHandler(fn: (err: ApiError) => void): void {
  onError = fn
}

/** FastAPI returns `detail` as a string, or as a list of validation errors. */
function readDetail(data: unknown, status: number): string {
  if (data && typeof data === 'object' && 'detail' in data) {
    const d = (data as { detail: unknown }).detail
    if (typeof d === 'string') return d
    if (Array.isArray(d) && d.length > 0) {
      const first = d[0] as { msg?: unknown }
      if (typeof first?.msg === 'string') return first.msg
    }
  }
  return status >= 500 || status === 0 ? '' : `HTTP ${status}`
}

async function parseBody(res: Response): Promise<unknown> {
  if (res.status === 204) return null
  const type = res.headers.get('content-type') ?? ''
  if (type.includes('application/json')) return res.json().catch(() => null)
  return null
}

/**
 * Tabs share one refresh (QA C-6). The refresh token rotates on every use and the server treats a second use
 * of the old one as theft, so two tabs refreshing at once used to sign the user out. Now:
 * - a Web Lock (`navigator.locks`) lets only one tab call /auth/refresh at a time; the others wait for it;
 * - the winner posts the new access token on a BroadcastChannel, so a tab that waited adopts it instead of
 *   spending the already-rotated cookie again.
 * Browsers without Web Locks still refresh, just without the cross-tab guard.
 */
const REFRESH_LOCK = 'oe-auth-refresh'
const SHARE_FRESH_MS = 15_000
const channel: BroadcastChannel | null = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel('oe-auth') : null
let shared: { token: string; at: number } | null = null
channel?.addEventListener('message', (e: MessageEvent<{ type?: string; token?: string }>) => {
  if (e.data?.type === 'token' && typeof e.data.token === 'string') shared = { token: e.data.token, at: Date.now() }
  else if (e.data?.type === 'logout') shared = null
})

/** Tell the other tabs that this one signed out, so none of them hands out a stale token. */
export function broadcastLogout(): void {
  shared = null
  try {
    channel?.postMessage({ type: 'logout' })
  } catch {
    /* channel closed */
  }
}

async function refreshOnce(staleToken: string | null): Promise<boolean> {
  // Another tab refreshed a moment ago: take its token instead of spending the rotated cookie.
  if (shared && shared.token !== staleToken && Date.now() - shared.at < SHARE_FRESH_MS) {
    setAccessToken(shared.token)
    return true
  }
  try {
    const res = await fetch(`${BASE}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
      headers: CSRF_HEADER,
    })
    if (!res.ok) return false
    const data = (await res.json()) as { access_token?: string | null }
    setAccessToken(data.access_token ?? null)
    if (data.access_token) {
      shared = { token: data.access_token, at: Date.now() }
      try {
        channel?.postMessage({ type: 'token', token: data.access_token })
      } catch {
        /* channel closed */
      }
    }
    return !!data.access_token
  } catch {
    return false
  }
}

/** Exchange the refresh cookie for a new access token. Shared by concurrent callers and across tabs. */
export function refreshAccess(): Promise<boolean> {
  const d = demo()
  if (d) {
    return d.restore().then((ok) => {
      setAccessToken(ok ? 'demo-access-token' : null)
      return ok
    })
  }
  if (!refreshing) {
    const stale = accessToken
    const locks = typeof navigator !== 'undefined' ? navigator.locks : undefined
    // A lock that can't be had (unsupported, page being torn down, a tab stuck for 10 s) must never cost the
    // session: fall back to a plain refresh.
    let ran = false
    const guarded = () => {
      ran = true
      return refreshOnce(stale)
    }
    const run: Promise<boolean> = locks
      ? locks
          .request(REFRESH_LOCK, { signal: AbortSignal.timeout?.(10_000) }, guarded)
          .then((v) => !!v, () => (ran ? false : refreshOnce(stale)))
      : refreshOnce(stale)
    const p = run.catch(() => false).finally(() => {
      if (refreshing === p) refreshing = null
    })
    refreshing = p
    return p
  }
  return refreshing
}

async function send(method: string, path: string, opts: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = { Accept: 'application/json', ...CSRF_HEADER, ...opts.headers }
  const isForm = opts.body instanceof FormData
  if (opts.body !== undefined && !isForm) headers['Content-Type'] = 'application/json'
  if (opts.auth !== false && accessToken) headers.Authorization = `Bearer ${accessToken}`
  return fetch(`${BASE}${path}`, {
    method,
    headers,
    credentials: 'include',
    body: opts.body === undefined ? undefined : isForm ? (opts.body as FormData) : JSON.stringify(opts.body),
    signal: opts.signal,
  })
}

export async function request<T>(method: string, path: string, opts: RequestOptions = {}): Promise<T> {
  const d = demo()
  if (d) {
    try {
      return (await d.request(method, path, opts)) as T
    } catch (e) {
      if (e instanceof ApiError && e.status === 401 && opts.auth !== false) onAuthLost?.()
      else if (e instanceof ApiError && !opts.silent) onError?.(e)
      throw e
    }
  }
  let res: Response
  try {
    res = await send(method, path, opts)
    if (res.status === 401 && opts.auth !== false) {
      const ok = await refreshAccess()
      if (!ok) {
        setAccessToken(null)
        onAuthLost?.()
        throw new ApiError(401, '')
      }
      res = await send(method, path, opts)
      if (res.status === 401) {
        setAccessToken(null)
        onAuthLost?.()
      }
    }
  } catch (e) {
    if (e instanceof ApiError) throw e
    if (e instanceof DOMException && e.name === 'AbortError') throw e
    const err = new ApiError(0, '')
    if (!opts.silent) onError?.(err)
    throw err
  }

  const data = await parseBody(res)
  if (!res.ok) {
    const retry = Number(res.headers.get('retry-after'))
    const err = new ApiError(res.status, readDetail(data, res.status), Number.isFinite(retry) && retry > 0 ? retry : null)
    if (res.status === 403 && /двухфактор/i.test(err.detail)) {
      // Background polls (counters, notifications) stay quiet; screens the user opened go to the 2FA setup.
      if (!opts.silent) onMfaRequired?.()
      throw err
    }
    // A lost session is handled by redirecting to /login, not by a toast.
    if (!opts.silent && !(res.status === 401 && opts.auth !== false)) onError?.(err)
    throw err
  }
  return data as T
}

/**
 * Download a file the API streams (Excel exports, templates). A plain link can't send the bearer token,
 * so we fetch the bytes and hand the browser a blob URL. Errors go through the same handler as JSON calls.
 */
export async function download(path: string, fallbackName: string): Promise<void> {
  const d = demo()
  if (d) return d.download()
  let res: Response
  try {
    res = await send('GET', path, {})
    if (res.status === 401 && (await refreshAccess())) res = await send('GET', path, {})
  } catch {
    const err = new ApiError(0, '')
    onError?.(err)
    throw err
  }
  if (!res.ok) {
    const err = new ApiError(res.status, readDetail(await parseBody(res), res.status))
    if (res.status === 401) {
      setAccessToken(null)
      onAuthLost?.()
    } else onError?.(err)
    throw err
  }
  const name = /filename="?([^";]+)"?/.exec(res.headers.get('content-disposition') ?? '')?.[1] ?? fallbackName
  const url = URL.createObjectURL(await res.blob())
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

/** `?a=1&b=x` from an object; empty, null and false values are skipped. */
export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '' || v === false) continue
    sp.set(k, String(v))
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

export const http = {
  get: <T>(path: string, opts?: RequestOptions) => request<T>('GET', path, opts),
  post: <T>(path: string, body?: unknown, opts?: RequestOptions) => request<T>('POST', path, { ...opts, body }),
  put: <T>(path: string, body?: unknown, opts?: RequestOptions) => request<T>('PUT', path, { ...opts, body }),
  patch: <T>(path: string, body?: unknown, opts?: RequestOptions) => request<T>('PATCH', path, { ...opts, body }),
  delete: <T = void>(path: string, opts?: RequestOptions) => request<T>('DELETE', path, opts),
}
