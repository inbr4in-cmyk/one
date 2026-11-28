// WhatsApp link by QR for the One English inbox ("как WhatsApp Web").
// A small local service: it keeps the linked-device sessions of the school's WhatsApp numbers (one per branch; line 0 is
// the number linked before branches had their own), hands the QR and the status to the
// API, passes new chat messages to the API and sends the answers managers type. It listens on 127.0.0.1 only and every
// call carries the shared secret. Unofficial protocol (Baileys): manual answers only, nothing automatic goes through it.
// Message texts are never written to the log.
import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import { timingSafeEqual } from 'node:crypto'
import makeWASocket, { Browsers, DisconnectReason, getContentType, jidDecode, normalizeMessageContent, useMultiFileAuthState } from 'baileys'
import pino from 'pino'

const PORT = Number(process.env.OE_WA_BRIDGE_PORT || 8720)
const SECRET = process.env.OE_WA_BRIDGE_SECRET || ''
const API = `http://127.0.0.1:${process.env.OE_PORT || 8000}/api/webhooks/wa-bridge`
const DIR = process.env.OE_WA_AUTH_DIR || '/var/lib/one-english/wa-auth'
const SPOOL = path.join(DIR, 'queue.json')
const SEND_GAP_MS = 1500 // answers leave at a human pace, one by one

if (SECRET.length < 24) {
  process.stderr.write('OE_WA_BRIDGE_SECRET is not set: the WhatsApp link is off\n')
  process.exit(0)
}
fs.mkdirSync(DIR, { recursive: true, mode: 0o700 })
// Our own lines go straight to stdout. Everything the libraries print through console is dropped: the Signal library
// prints whole session objects, keys included («Closing session: …»), and that must never reach the system journal.
const log = (...a) => process.stdout.write(`${new Date().toISOString()} ${a.join(' ')}\n`)
for (const k of ['log', 'info', 'warn', 'error', 'debug', 'trace', 'dir', 'table']) console[k] = () => {}
const quiet = pino({ level: 'silent' })

function readJson(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'))
  } catch {
    return fallback
  }
}
function writeJson(file, value) {
  fs.writeFileSync(file + '.tmp', JSON.stringify(value), { mode: 0o600 })
  fs.renameSync(file + '.tmp', file)
}

// ---------- to the API ----------
let queue = readJson(SPOOL, [])
let flushing = false
async function flush() {
  if (flushing) return
  flushing = true
  try {
    while (queue.length) {
      const batch = queue.slice(0, 50)
      const r = await fetch(API, { method: 'POST', headers: { 'content-type': 'application/json', 'x-bridge-secret': SECRET }, body: JSON.stringify({ events: batch }), signal: AbortSignal.timeout(15000) })
      if (!r.ok) throw new Error(`API answered ${r.status}`)
      queue = queue.slice(batch.length)
      writeJson(SPOOL, queue)
    }
  } catch (e) {
    log('API is not reachable, will retry:', String(e.message || e).slice(0, 120))
  } finally {
    flushing = false
  }
}
function push(ev) {
  queue.push(ev)
  if (queue.length > 5000) queue = queue.slice(-5000)
  writeJson(SPOOL, queue)
  void flush()
}
setInterval(() => queue.length && void flush(), 5000)

// ---------- WhatsApp ----------
const isPerson = (jid) => typeof jid === 'string' && (jid.endsWith('@s.whatsapp.net') || jid.endsWith('@lid'))
const digits = (jid) => jidDecode(jid)?.user?.replace(/\D/g, '') || null
const jidOf = (chat) => (chat.startsWith('lid:') ? `${chat.slice(4)}@lid` : `${chat.replace(/\D/g, '')}@s.whatsapp.net`)

/** What the message is for the inbox: kind + text. null for service messages (reactions, receipts, key exchange…). */
function describe(message) {
  const m = normalizeMessageContent(message)
  const type = m && getContentType(m)
  if (!type) return null
  const c = m[type]
  switch (type) {
    case 'conversation':
      return { kind: 'text', text: String(c) }
    case 'extendedTextMessage':
      return { kind: 'text', text: c?.text ?? '' }
    case 'imageMessage':
      return { kind: 'image', text: c?.caption || null }
    case 'audioMessage':
      return { kind: 'audio', text: null }
    case 'videoMessage':
    case 'documentMessage':
    case 'stickerMessage':
      return { kind: 'file', text: c?.caption || (type === 'stickerMessage' ? 'Стикер' : type === 'videoMessage' ? 'Видео' : c?.fileName || null) }
    case 'locationMessage':
    case 'liveLocationMessage':
      return { kind: 'text', text: 'Геолокация' }
    case 'contactMessage':
    case 'contactsArrayMessage':
      return { kind: 'text', text: `Контакт: ${c?.displayName ?? ''}`.trim() }
    default:
      return null
  }
}

/** One linked number. Line 0 keeps its files where the single link kept them, so that link goes on after the update. */
function makeLine(id) {
  const home = id === 0 ? DIR : path.join(DIR, `line-${id}`)
  const AUTH = path.join(home, 'session')
  const META = path.join(home, 'meta.json')
  fs.mkdirSync(AUTH, { recursive: true, mode: 0o700 })
  /** off | qr | connecting | open | logged_out | banned */
  let state = 'off'
  let qr = null
  let me = null
  let sock = null
  let wanted = false // somebody asked to connect (or a saved session exists): reconnect after a drop
  let retry = 0
  let lastClose = null // the code of the last drop, shown on the settings page when the link does not come up
  let meta = readJson(META, {}) // { linked_at } — messages older than the link are history and are not taken
  const sentByUs = new Set()
  const tag = `[${id}]`

  const hasSession = () => fs.existsSync(path.join(AUTH, 'creds.json'))
  function wipe() {
    fs.rmSync(AUTH, { recursive: true, force: true })
    fs.mkdirSync(AUTH, { recursive: true, mode: 0o700 })
    meta = {}
    writeJson(META, meta)
  }

  /** The chat as the API knows it: the phone number in digits, or "lid:…" when WhatsApp hides the number. */
  async function chatOf(key) {
    const jid = key.remoteJid
    if (jid.endsWith('@s.whatsapp.net')) return { chat: digits(jid), phone: digits(jid) }
    let pn = key.remoteJidAlt && key.remoteJidAlt.endsWith('@s.whatsapp.net') ? key.remoteJidAlt : null
    if (!pn) {
      try {
        pn = await sock?.signalRepository?.lidMapping?.getPNForLID(jid)
      } catch {
        pn = null
      }
    }
    const phone = pn ? digits(pn) : null
    return phone ? { chat: phone, phone } : { chat: `lid:${jidDecode(jid)?.user}`, phone: null }
  }

  async function onMessages({ messages }) {
    for (const msg of messages ?? []) {
      try {
        const key = msg.key
        if (!key?.id || !isPerson(key.remoteJid)) continue // groups, statuses, channels and broadcasts are not taken
        const ts = Number(msg.messageTimestamp || 0)
        if (!meta.linked_at || ts < meta.linked_at) continue // history from before the link stays on the phone
        if (key.fromMe && sentByUs.delete(key.id)) continue // our own answer, already stored by the API
        const what = describe(msg.message)
        if (!what) continue
        const { chat, phone } = await chatOf(key)
        if (!chat) continue
        push({ line: id, type: key.fromMe ? 'out' : 'in', id: key.id, chat, phone, name: key.fromMe ? null : msg.pushName || null, kind: what.kind, text: what.text ? String(what.text).slice(0, 4000) : null, ts })
      } catch (e) {
        log(tag, 'message skipped:', String(e.message || e).slice(0, 120))
      }
    }
  }

  function fail(e) {
    sock = null
    state = 'off'
    log(tag, 'connect failed:', String(e?.message || e).slice(0, 160))
  }

  async function connect() {
    if (sock) return
    wanted = true
    state = hasSession() ? 'connecting' : 'qr'
    qr = null
    const { state: auth, saveCreds } = await useMultiFileAuthState(AUTH)
    const s = makeWASocket({
      auth, logger: quiet, browser: Browsers.ubuntu('One English'), markOnlineOnConnect: false, syncFullHistory: false,
      shouldSyncHistoryMessage: () => false, generateHighQualityLinkPreview: false,
      shouldIgnoreJid: (jid) => !isPerson(jid),
    })
    sock = s
    s.ev.on('creds.update', saveCreds)
    s.ev.on('messages.upsert', (u) => void onMessages(u))
    s.ev.on('connection.update', (u) => {
      if (sock !== s) return
      if (u.qr) {
        state = 'qr'
        qr = u.qr
      }
      if (u.connection === 'open') {
        state = 'open'
        qr = null
        retry = 0
        lastClose = null
        me = { phone: digits(s.user?.id ?? ''), name: s.user?.name ?? null }
        if (!meta.linked_at) {
          meta = { linked_at: Math.floor(Date.now() / 1000) }
          writeJson(META, meta)
        }
        log(tag, 'linked', me.phone ? `…${me.phone.slice(-4)}` : '')
      }
      if (u.connection === 'close') {
        const code = u.lastDisconnect?.error?.output?.statusCode
        sock = null
        qr = null
        log(tag, 'closed', code ?? '')
        lastClose = code ?? null
        if (code === DisconnectReason.loggedOut) {
          // unlinked on the phone (WhatsApp → Связанные устройства) or the session is no longer valid
          wipe()
          me = null
          wanted = false
          state = 'logged_out'
        } else if (code === DisconnectReason.forbidden) {
          wanted = false
          state = 'banned'
        } else if (code === DisconnectReason.connectionReplaced) {
          wanted = false
          state = 'off' // the same session was opened elsewhere: do not fight for it
        } else if (hasSession() && wanted) {
          state = 'connecting'
          setTimeout(() => void connect().catch(fail), code === DisconnectReason.restartRequired ? 500 : Math.min(60000, 2000 * 2 ** retry++))
        } else {
          wanted = false
          state = 'off' // nobody scanned the QR in time
        }
      }
    })
  }

  let lastSend = Promise.resolve()
  function send(chat, text) {
    const job = lastSend.then(async () => {
      if (state !== 'open' || !sock) throw new Error('WhatsApp не подключён')
      const r = await sock.sendMessage(jidOf(chat), { text })
      const mid = r?.key?.id
      if (mid) {
        sentByUs.add(mid)
        setTimeout(() => sentByUs.delete(mid), 600000)
      }
      await new Promise((ok) => setTimeout(ok, SEND_GAP_MS))
      return mid
    })
    lastSend = job.catch(() => undefined)
    return job
  }

  async function logout() {
    wanted = false
    const s = sock
    sock = null
    try {
      await s?.logout()
    } catch {
      /* already closed */
    }
    wipe()
    me = null
    qr = null
    state = 'off'
  }

  return {
    hasSession, send, logout,
    start: async () => {
      if (state !== 'open') await connect().catch(fail)
    },
    status: () => ({ state, qr, me, linked_at: meta.linked_at ?? null, pending: queue.length, last_close: lastClose }),
  }
}

const lines = new Map()
const lineId = (v) => (v === undefined || v === null ? 0 : Number.isInteger(v) && v >= 0 && v <= 1000000 ? v : null)
function line(id) {
  if (!lines.has(id)) lines.set(id, makeLine(id))
  return lines.get(id)
}

// ---------- local HTTP for the API ----------
const authed = (req) => {
  const got = Buffer.from(String(req.headers['x-bridge-secret'] || ''))
  const want = Buffer.from(SECRET)
  return got.length === want.length && timingSafeEqual(got, want)
}
function body(req) {
  return new Promise((ok, bad) => {
    let s = ''
    req.on('data', (d) => {
      s += d
      if (s.length > 20000) bad(new Error('too large'))
    })
    req.on('end', () => {
      try {
        ok(s ? JSON.parse(s) : {})
      } catch (e) {
        bad(e)
      }
    })
    req.on('error', bad)
  })
}
const OFF = { state: 'off', qr: null, me: null, linked_at: null, last_close: null }
const statusOf = (id) => (lines.has(id) ? lines.get(id).status() : { ...OFF, pending: queue.length })

http.createServer(async (req, res) => {
  const reply = (code, obj) => {
    res.writeHead(code, { 'content-type': 'application/json' })
    res.end(JSON.stringify(obj))
  }
  try {
    if (!authed(req)) return reply(401, { error: 'unauthorized' })
    if (req.method === 'GET' && req.url === '/status') {
      return reply(200, { lines: Object.fromEntries([...lines].map(([id, l]) => [id, l.status()])) })
    }
    if (req.method !== 'POST') return reply(404, { error: 'not found' })
    const b = await body(req)
    const id = lineId(b.line)
    if (id === null) return reply(400, { error: 'bad line' })
    if (req.url === '/start') {
      await line(id).start()
      return reply(200, statusOf(id))
    }
    if (req.url === '/logout') {
      if (lines.has(id)) await lines.get(id).logout()
      return reply(200, statusOf(id))
    }
    if (req.url === '/send') {
      if (typeof b.to !== 'string' || typeof b.text !== 'string' || !b.text.trim() || !/^(lid:)?\d{5,20}$/.test(b.to)) return reply(400, { error: 'bad request' })
      if (!lines.has(id)) return reply(503, { error: 'WhatsApp не подключён' })
      try {
        return reply(200, { id: await lines.get(id).send(b.to, b.text.slice(0, 4096)) })
      } catch (e) {
        return reply(503, { error: String(e.message || e).slice(0, 200) })
      }
    }
    reply(404, { error: 'not found' })
  } catch (e) {
    reply(500, { error: String(e.message || e).slice(0, 200) })
  }
}).listen(PORT, '127.0.0.1', () => log(`WhatsApp link service on 127.0.0.1:${PORT}`))

process.on('unhandledRejection', (e) => log('unhandled:', String(e?.message || e).slice(0, 160)))
process.on('uncaughtException', (e) => log('uncaught:', String(e?.message || e).slice(0, 160)))
// Every number that was linked before the restart comes back by itself.
const saved = [0, ...fs.readdirSync(DIR).map((n) => /^line-(\d{1,7})$/.exec(n)).filter(Boolean).map((m) => Number(m[1]))]
for (const id of saved) {
  if (fs.existsSync(path.join(id === 0 ? DIR : path.join(DIR, `line-${id}`), 'session', 'creds.json'))) void line(id).start()
}
