/**
 * Level and stage colors come from the API as hex. Known hexes map to theme tokens so the dark
 * theme gets its own shades; anything else is used as is.
 */
const TOKENS: Record<string, string> = {
  '#2e9a6e': 'var(--lv-beg)',
  '#1a6fd1': 'var(--lv-ele)',
  '#c9631a': 'var(--lv-pre)',
  '#7b52c7': 'var(--lv-int)',
  '#b08900': 'var(--lv-up)',
  '#c2417f': 'var(--lv-ielts)',
  '#0e8fa8': 'var(--lv-kids)',
  '#1e8e5a': 'var(--ok)',
  '#c98a06': 'var(--warn)',
  '#5b6782': 'var(--muted)',
}

export function tone(hex: string | null | undefined): string {
  if (!hex) return 'var(--muted)'
  return TOKENS[hex.toLowerCase()] ?? hex
}
