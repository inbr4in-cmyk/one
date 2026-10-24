/** Names the server may use for sprite icons that are called differently here */
const ALIAS: Record<string, string> = { pen: 'pencil', mug: 'cup', hoodie: 'shirt', tshirt: 'shirt' }

/** Icon name if the sprite has it, else the fallback (server data may name icons the sprite lacks). */
export function iconOr(name: string | null | undefined, fallback: string): string {
  const n = name ? ALIAS[name] ?? name : null
  if (!n || typeof document === 'undefined') return fallback
  return document.getElementById(`i-${n}`) ? n : fallback
}
