import { ApiError } from '@/api/http'

/** The server's own message for a failed call, or null for network/unknown errors. */
export function apiErr(e: unknown): string | null {
  return e instanceof ApiError && e.detail ? e.detail : null
}
