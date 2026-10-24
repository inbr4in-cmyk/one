import { onBeforeUnmount, onMounted, ref } from 'vue'
import { notifyApi } from '@/api/chats'

/**
 * One WebSocket per tab. A short-lived ticket from POST /api/ws/ticket authenticates it, so the
 * access token never goes into a URL. Reconnects with exponential backoff (1s → 30s, jittered).
 */
export interface RealtimeEvent {
  type: string
  [key: string]: unknown
}
type Handler = (e: RealtimeEvent) => void

const handlers = new Map<string, Set<Handler>>()
let socket: WebSocket | null = null
let stopped = true
let attempt = 0
let retryTimer: ReturnType<typeof setTimeout> | undefined
let pingTimer: ReturnType<typeof setInterval> | undefined
export const realtimeConnected = ref(false)

function emit(e: RealtimeEvent) {
  handlers.get(e.type)?.forEach((h) => h(e))
  handlers.get('*')?.forEach((h) => h(e))
}

function scheduleReconnect() {
  if (stopped) return
  clearTimeout(retryTimer)
  const base = Math.min(30_000, 1000 * 2 ** attempt)
  attempt++
  retryTimer = setTimeout(connect, base * (0.5 + Math.random() / 2))
}

async function connect() {
  if (stopped || socket) return
  let ticket: string
  try {
    ticket = (await notifyApi.wsTicket()).ticket
  } catch {
    scheduleReconnect()
    return
  }
  if (stopped) return
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${proto}://${location.host}/api/ws?ticket=${encodeURIComponent(ticket)}`)
  socket = ws
  ws.onopen = () => {
    const wasReconnect = attempt > 0
    attempt = 0
    realtimeConnected.value = true
    clearInterval(pingTimer)
    pingTimer = setInterval(() => ws.readyState === WebSocket.OPEN && ws.send('ping'), 25_000)
    emit({ type: 'realtime.open', reconnect: wasReconnect })
  }
  ws.onmessage = (m) => {
    try {
      const data = JSON.parse(String(m.data)) as RealtimeEvent
      if (data && typeof data.type === 'string' && data.type !== 'pong') emit(data)
    } catch {
      /* ignore malformed frames */
    }
  }
  ws.onclose = () => {
    if (socket === ws) socket = null
    realtimeConnected.value = false
    clearInterval(pingTimer)
    scheduleReconnect()
  }
}

function wake() {
  if (!stopped && !socket) {
    attempt = 0
    clearTimeout(retryTimer)
    connect()
  }
}

export function startRealtime() {
  if (!stopped) return
  stopped = false
  window.addEventListener('online', wake)
  document.addEventListener('visibilitychange', wake)
  connect()
}

export function stopRealtime() {
  stopped = true
  clearTimeout(retryTimer)
  clearInterval(pingTimer)
  window.removeEventListener('online', wake)
  document.removeEventListener('visibilitychange', wake)
  socket?.close()
  socket = null
  attempt = 0
}

export function onRealtime(type: string, handler: Handler): () => void {
  if (!handlers.has(type)) handlers.set(type, new Set())
  handlers.get(type)!.add(handler)
  return () => handlers.get(type)?.delete(handler)
}

/** Subscribe for the lifetime of the calling component. */
export function useRealtime(type: string, handler: Handler) {
  let off: (() => void) | null = null
  onMounted(() => (off = onRealtime(type, handler)))
  onBeforeUnmount(() => off?.())
}
