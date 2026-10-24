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
const CSRF_HEADER = { 'X-Requested-With': 'one-english' }

let accessToken: string | null = null
let refreshing: Promise<boolean> | null = null

type Handler<T> = ((arg: T) => void) | null
let onAuthLost: Handler<void> = null
let onError: Handler<ApiError> = null

export class ApiError extends Error {
  readonly status: number
  readonly detail: string
  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export interface RequestOptions {
  body?: unknown
  /** Send the bearer token and refresh on 401. Default true. */
  auth?: boolean
  /** Do not show an error toast; the caller handles the error. */
  silent?: boolean
  signal?: AbortSignal
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

/** Exchange the refresh cookie for a new access token. Shared by concurrent callers. */
export function refreshAccess(): Promise<boolean> {
  if (!refreshing) {
    refreshing = (async () => {
      try {
        const res = await fetch(`${BASE}/auth/refresh`, {
          method: 'POST',
          credentials: 'include',
          headers: CSRF_HEADER,
        })
        if (!res.ok) return false
        const data = (await res.json()) as { access_token?: string | null }
        setAccessToken(data.access_token ?? null)
        return !!data.access_token
      } catch {
        return false
      }
    })().finally(() => {
      refreshing = null
    })
  }
  return refreshing
}

async function send(method: string, path: string, opts: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = { Accept: 'application/json', ...CSRF_HEADER }
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json'
  if (opts.auth !== false && accessToken) headers.Authorization = `Bearer ${accessToken}`
  return fetch(`${BASE}${path}`, {
    method,
    headers,
    credentials: 'include',
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
    signal: opts.signal,
  })
}

export async function request<T>(method: string, path: string, opts: RequestOptions = {}): Promise<T> {
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
    const err = new ApiError(res.status, readDetail(data, res.status))
    // A lost session is handled by redirecting to /login, not by a toast.
    if (!opts.silent && !(res.status === 401 && opts.auth !== false)) onError?.(err)
    throw err
  }
  return data as T
}

export const http = {
  get: <T>(path: string, opts?: RequestOptions) => request<T>('GET', path, opts),
  post: <T>(path: string, body?: unknown, opts?: RequestOptions) => request<T>('POST', path, { ...opts, body }),
  put: <T>(path: string, body?: unknown, opts?: RequestOptions) => request<T>('PUT', path, { ...opts, body }),
  patch: <T>(path: string, body?: unknown, opts?: RequestOptions) => request<T>('PATCH', path, { ...opts, body }),
  delete: <T = void>(path: string, opts?: RequestOptions) => request<T>('DELETE', path, opts),
}
