/** Only http(s) or same-origin links may be rendered as hrefs; anything else (javascript:, data:) is dropped. */
export function safeUrl(u: string | null | undefined): string | null {
  if (!u) return null
  return /^https?:\/\//i.test(u) || (u.startsWith('/') && !u.startsWith('//')) ? u : null
}
