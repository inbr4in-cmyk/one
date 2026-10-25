/**
 * Demo build only: an in-memory stand-in for the API. GETs are answered from fixtures recorded against the
 * demo seed (one set per role); the common actions change that data in memory so they visibly work, and
 * everything else succeeds with a toast. Nothing leaves the browser.
 */
import { ApiError, type RequestOptions } from '@/api/http'
import { useToastStore } from '@/stores/toast'
import { readPref, writePref } from '@/utils/storage'
import { DEMO_NOTICE, DEMO_PHONES, type DemoRole } from './meta'

interface Fixture {
  captured_at: string
  responses: Record<string, unknown>
}

type Json = Record<string, unknown>
type Row = Record<string, unknown> & { id?: number }

const loaders: Record<DemoRole, () => Promise<{ default: unknown }>> = {
  owner: () => import('./fixtures/owner.json'),
  admin: () => import('./fixtures/admin.json'),
  manager: () => import('./fixtures/manager.json'),
  teacher: () => import('./fixtures/teacher.json'),
}

const ROLE_KEY = 'oe-demo-role'
const SCHOOL_OFFSET_MS = 5 * 3600_000 // Asia/Almaty, UTC+5 all year

let role: DemoRole | null = null
/** pathname -> list of [canonical query, data] */
let db = new Map<string, { q: URLSearchParams; data: unknown }[]>()
let seq = 900_000

export function storedRole(): DemoRole | null {
  const r = readPref(ROLE_KEY)
  return r && r in loaders ? (r as DemoRole) : null
}

export async function useRole(r: DemoRole): Promise<void> {
  if (role === r && db.size) return
  const mod = await loaders[r]()
  const fx = structuredClone(mod.default) as Fixture
  db = new Map()
  for (const [key, data] of Object.entries(fx.responses)) {
    const { pathname, q } = parse(key)
    const list = db.get(pathname) ?? []
    list.push({ q, data })
    db.set(pathname, list)
  }
  role = r
  writePref(ROLE_KEY, r)
}

export function forgetRole(): void {
  role = null
  db = new Map()
  writePref(ROLE_KEY, null)
}

function parse(path: string): { pathname: string; q: URLSearchParams } {
  const u = new URL(path, 'http://demo.local')
  const cmp = (x: string, y: string) => (x < y ? -1 : x > y ? 1 : 0)
  const entries = [...u.searchParams.entries()].sort((a, b) => cmp(a[0], b[0]) || cmp(a[1], b[1]))
  return { pathname: u.pathname, q: new URLSearchParams(entries) }
}

const clone = <T>(v: T): T => (v === undefined || v === null ? v : structuredClone(v))
const nowIso = () => new Date().toISOString()
const nextId = () => ++seq

function notice() {
  useToastStore().show(DEMO_NOTICE, 'info', 2600)
}

/** Works both as a list and as a page ({ items, total }) for endpoints nobody recorded. */
function emptyAny(): unknown {
  return Object.assign([], { items: [], total: 0, limit: 50, offset: 0 })
}

// ---------- reads

function exact(pathname: string, q: URLSearchParams): unknown | undefined {
  const s = q.toString()
  return db.get(pathname)?.find((e) => e.q.toString() === s)?.data
}

/** Recorded variants of a path, the one sharing the most query values first. */
function nearest(pathname: string, q: URLSearchParams): unknown | undefined {
  const list = db.get(pathname)
  if (!list?.length) return undefined
  let best: (typeof list)[number] | undefined
  let bestScore = -Infinity
  for (const e of list) {
    let score = 0
    for (const [k, v] of q) {
      if (e.q.get(k) === v) score += 2
      else if (e.q.has(k)) score -= 1
    }
    for (const k of e.q.keys()) if (!q.has(k)) score -= 0.5
    if (score > bestScore) {
      best = e
      bestScore = score
    }
  }
  return best?.data
}

/** Same route with another id (e.g. /students/7 when only /students/12 was recorded). */
function sibling(pathname: string): unknown | undefined {
  if (!/\/\d+(\/|$)/.test(pathname)) return undefined
  const shape = pathname.replace(/\/\d+(?=\/|$)/g, '/#')
  for (const [p, list] of db) {
    if (p.replace(/\/\d+(?=\/|$)/g, '/#') === shape && list[0]) {
      const d = list[0].data
      return Array.isArray(d) ? [] : d
    }
  }
  return undefined
}

function all(pathname: string): unknown[] {
  return (db.get(pathname) ?? []).map((e) => e.data)
}

/** Each recorded array (or page.items) under these paths, for in-place updates. */
function lists(test: (pathname: string) => boolean): Row[][] {
  const out: Row[][] = []
  for (const [p, list] of db) {
    if (!test(p)) continue
    for (const e of list) {
      const d = e.data as { items?: unknown }
      if (Array.isArray(d)) out.push(d as Row[])
      else if (d && Array.isArray(d.items)) out.push(d.items as Row[])
    }
  }
  return out
}

function put(path: string, data: unknown) {
  const { pathname, q } = parse(path)
  const list = db.get(pathname) ?? []
  const s = q.toString()
  const hit = list.find((e) => e.q.toString() === s)
  if (hit) hit.data = data
  else list.push({ q, data })
  db.set(pathname, list)
}

const localDay = (iso: string) => new Date(Date.parse(iso) + SCHOOL_OFFSET_MS).toISOString().slice(0, 10)

function lessonsFor(q: URLSearchParams): Row[] {
  const seen = new Map<number, Row>()
  for (const d of all('/lessons')) if (Array.isArray(d)) for (const l of d as Row[]) seen.set(l.id as number, l)
  const from = q.get('from') ?? '0000'
  const to = q.get('to') ?? '9999'
  const eq = (k: string) => (l: Row) => !q.get(k) || String(l[k]) === q.get(k)
  return [...seen.values()]
    .filter((l) => {
      const day = localDay(l.starts_at as string)
      return day >= from && day <= to
    })
    .filter(eq('branch_id'))
    .filter(eq('group_id'))
    .filter(eq('teacher_id'))
    .filter(eq('room_id'))
    .filter((l) => q.get('include_cancelled') === 'true' || l.status !== 'cancelled')
    .sort((a, b) => String(a.starts_at).localeCompare(String(b.starts_at)))
}

function searchFor(text: string): unknown {
  const needle = text.trim().toLowerCase()
  const out: Record<string, Row[]> = { students: [], leads: [], groups: [], staff: [] }
  const seen = new Set<string>()
  for (const d of all('/search')) {
    for (const [k, rows] of Object.entries((d ?? {}) as Record<string, Row[]>)) {
      for (const r of rows ?? []) {
        const id = `${k}:${r.id}`
        if (seen.has(id) || !String(r.title ?? '').toLowerCase().includes(needle)) continue
        seen.add(id)
        ;(out[k] ??= []).push(r)
      }
    }
  }
  return out
}

function read(pathname: string, q: URLSearchParams): unknown {
  const hit = exact(pathname, q)
  if (hit !== undefined) return clone(hit)
  if (pathname === '/lessons') return lessonsFor(q)
  if (pathname === '/search') return searchFor(q.get('q') ?? '')
  const msgs = /^\/(chats|inbox\/conversations)\/(\d+)\/messages$/.exec(pathname)
  if (msgs) {
    const base = (exact(pathname, new URLSearchParams()) as Row[] | undefined) ?? []
    const after = Number(q.get('after_id'))
    if (after) return clone(base.filter((m) => (m.id as number) > after))
    if (q.get('before_id')) return []
    return clone(base)
  }
  const near = nearest(pathname, q)
  if (near !== undefined) return clone(near)
  const sib = sibling(pathname)
  if (sib !== undefined) return clone(sib)
  return emptyAny()
}

// ---------- writes

function me(): Row {
  return (exact('/auth/me', new URLSearchParams()) as Row) ?? { id: 0, full_name: 'Демо' }
}

function merge(target: unknown, patch: Json) {
  if (target && typeof target === 'object' && !Array.isArray(target)) Object.assign(target, patch)
}

type Handler = (m: RegExpExecArray, body: Json) => unknown

const handlers: [string, RegExp, Handler][] = [
  ['POST', /^\/auth\/login$/, () => token()],
  ['POST', /^\/auth\/mfa$/, () => token()],
  ['POST', /^\/auth\/otp\/request$/, () => null],
  ['POST', /^\/auth\/logout$/, () => (forgetRole(), null)],
  ['POST', /^\/ws\/ticket$/, () => ({ ticket: 'demo' })],

  // chats
  ['POST', /^\/chats\/(\d+)\/messages$/, (m, body) => {
    const chatId = Number(m[1])
    const u = me()
    const msg: Row = {
      id: nextId(), chat_id: chatId, sender_id: u.id, sender_name: u.full_name, sender_kind: 'staff', at: nowIso(),
      kind: body.kind ?? 'text', text: body.text ?? null, file_url: null, file_name: body.file_name ?? null,
      pinned: false, edited: false, hidden: false,
    }
    const path = `/chats/${chatId}/messages`
    const list = (exact(path, new URLSearchParams()) as Row[] | undefined) ?? []
    list.push(msg)
    put(path, list)
    for (const l of lists((p) => p === '/chats' || p === '/chats/monitor')) {
      const i = l.findIndex((c) => c.id === chatId)
      if (i < 0) continue
      l[i] = { ...l[i], last_message: { text: msg.text ?? msg.file_name ?? '', at: msg.at, sender: u.full_name } }
      l.unshift(...l.splice(i, 1))
    }
    return clone(msg)
  }],
  ['POST', /^\/chats\/(\d+)\/read$/, (m) => {
    for (const l of lists((p) => p === '/chats')) for (const c of l) if (c.id === Number(m[1])) c.unread = 0
    return null
  }],
  ['POST', /^\/chats\/direct$/, (_m, body) => {
    for (const l of lists((p) => p === '/chats')) {
      const c = l.find((x) => (x.other_user as Row | null)?.id === body.user_id)
      if (c) return clone(c)
    }
    const contact = lists((p) => p === '/chats/contacts').flat().find((x) => x.id === body.user_id) ?? { id: body.user_id, full_name: 'Сотрудник', kind: 'staff', position: null }
    const chat: Row = { id: nextId(), kind: 'direct', title: contact.full_name, group_id: null, unread: 0, last_message: null, other_user: contact, members: 2 }
    const chats = (exact('/chats', new URLSearchParams()) as Row[] | undefined) ?? []
    chats.unshift(chat)
    put('/chats', chats)
    put(`/chats/${chat.id}/messages`, [])
    put(`/chats/${chat.id}/pinned`, [])
    return clone(chat)
  }],

  // inbox
  ['POST', /^\/inbox\/conversations\/(\d+)\/(messages|template)$/, (m, body) => {
    const id = Number(m[1])
    let text = (body.text as string | undefined) ?? null
    if (m[2] === 'template') {
      const t = lists((p) => p === '/message-templates').flat().find((x) => x.code === body.code) as Row | undefined
      text = String(t?.body ?? body.code)
      for (const [k, v] of Object.entries((body.variables ?? {}) as Record<string, string>)) text = text.replaceAll(`{{${k}}}`, v).replaceAll(`{${k}}`, v)
    }
    const msg: Row = { id: nextId(), at: nowIso(), direction: 'out', kind: 'text', text, media_url: null, status: 'sent', sender_id: me().id }
    const path = `/inbox/conversations/${id}/messages`
    const list = (exact(path, new URLSearchParams()) as Row[] | undefined) ?? []
    list.push(msg)
    put(path, list)
    for (const l of lists((p) => p === '/inbox/conversations')) for (const c of l) if (c.id === id) Object.assign(c, { last_preview: text, last_message_at: msg.at, unread: 0 })
    return clone(msg)
  }],
  ['PATCH', /^\/inbox\/conversations\/(\d+)$/, (m, body) => {
    const id = Number(m[1])
    const conv = read(`/inbox/conversations/${id}`, new URLSearchParams()) as Row
    Object.assign(conv, body)
    put(`/inbox/conversations/${id}`, conv)
    for (const l of lists((p) => p === '/inbox/conversations')) for (const c of l) if (c.id === id) Object.assign(c, body)
    return clone(conv)
  }],

  // CRM
  ['POST', /^\/crm\/leads\/(\d+)\/stage$/, (m, body) => moveLead(Number(m[1]), Number(body.stage_id), (body.lost_reason as string) ?? null)],
  ['POST', /^\/crm\/leads\/(\d+)\/events$/, (m, body) => {
    const ev: Row = { id: nextId(), at: nowIso(), kind: body.kind, text: body.text, actor_id: me().id, meta: body.result ? { result: body.result } : {} }
    const d = exact(`/crm/leads/${m[1]}`, new URLSearchParams()) as { events?: Row[]; lead?: Row } | undefined
    if (d?.events) d.events.unshift(ev)
    if (d?.lead) d.lead.last_activity_at = ev.at
    return clone(ev)
  }],
  ['POST', /^\/crm\/leads$/, (_m, body) => {
    const lead: Row = {
      id: nextId(), full_name: body.full_name, phone: body.phone ?? null, age: body.age ?? null, parent_name: body.parent_name ?? null,
      parent_phone: body.parent_phone ?? null, branch_id: body.branch_id, pipeline_id: 1, stage_id: 0, stage_changed_at: nowIso(),
      source: body.source, owner_id: me().id, owner_name: me().full_name, assignee_id: null, student_id: null, level_id: body.level_id ?? null,
      placement_score: null, trial_lesson_id: null, trial_at: null, lost_reason: null, next_action_at: null, last_activity_at: nowIso(),
      notes: body.notes ?? null, is_hot: false, created_at: nowIso(), stale: false, waiting_min: null, channel: null, conversation_id: null,
    }
    for (const b of all('/crm/board') as { columns?: { stage: Row; total: number; leads: Row[] }[] }[]) {
      const col = b?.columns?.[0]
      if (!col) continue
      lead.stage_id = col.stage.id
      col.leads.unshift({ ...lead })
      col.total++
    }
    put(`/crm/leads/${lead.id}`, { lead, events: [{ id: nextId(), at: nowIso(), kind: 'created', text: null, actor_id: me().id, meta: {} }], tests: [] })
    return clone(lead)
  }],
  ['PATCH', /^\/crm\/leads\/(\d+)$/, (m, body) => {
    const id = Number(m[1])
    const d = exact(`/crm/leads/${id}`, new URLSearchParams()) as { lead?: Row } | undefined
    if (d?.lead) Object.assign(d.lead, body)
    for (const b of all('/crm/board') as { columns?: { leads: Row[] }[] }[]) for (const c of b?.columns ?? []) for (const l of c.leads) if (l.id === id) Object.assign(l, body)
    return clone(d?.lead ?? { id, ...body })
  }],

  // attendance
  ['PUT', /^\/lessons\/(\d+)\/attendance$/, (m, body) => {
    const path = `/lessons/${m[1]}/attendance`
    const roster = read(path, new URLSearchParams()) as { lesson?: Row; rows?: Row[] }
    for (const mark of (body.marks ?? []) as Row[]) {
      const row = roster.rows?.find((r) => (mark.student_id != null && r.student_id === mark.student_id) || (mark.lead_id != null && r.lead_id === mark.lead_id))
      if (row) Object.assign(row, { status: mark.status, grade: mark.grade, comment: mark.comment, stars: mark.stars })
    }
    if (roster.lesson) {
      roster.lesson.attendance_marked_at = nowIso()
      if (body.topic !== undefined) roster.lesson.topic = body.topic
      for (const l of lists((p) => p === '/lessons')) for (const x of l) if (x.id === roster.lesson.id) Object.assign(x, { attendance_marked_at: roster.lesson.attendance_marked_at, topic: roster.lesson.topic })
    }
    put(path, roster)
    return clone(roster)
  }],

  // tasks
  ['POST', /^\/tasks$/, (_m, body) => {
    const staff = lists((p) => p === '/staff-directory').flat()
    const u = me()
    const task: Row = {
      id: nextId(), title: body.title, description: body.description ?? null, creator_id: u.id, creator_name: u.full_name,
      branch_id: body.branch_id ?? null, priority: body.priority ?? 'normal', due_at: body.due_at ?? null, status: 'new', done_at: null,
      overdue: false, link_type: body.link_type ?? null, link_id: body.link_id ?? null, link_title: null, recurrence: body.recurrence ?? null,
      assignees: ((body.assignee_ids ?? []) as number[]).map((id) => ({ id, full_name: String(staff.find((s) => s.id === id)?.full_name ?? '') })),
      comments: 0, created_at: nowIso(),
    }
    for (const [p, list] of db) {
      if (p !== '/tasks') continue
      for (const e of list) {
        const box = e.q.get('box')
        const mine = (task.assignees as Row[]).some((a) => a.id === u.id)
        if (box === 'created' || box === 'all' || (box === 'mine' && mine)) {
          const page = e.data as { items: Row[]; total: number }
          page.items.unshift({ ...task })
          page.total++
        }
      }
    }
    put(`/tasks/${task.id}`, task)
    put(`/tasks/${task.id}/comments`, [])
    return clone(task)
  }],
  ['PATCH', /^\/tasks\/(\d+)$/, (m, body) => {
    const id = Number(m[1])
    const patch: Json = { ...body }
    if (body.status === 'done') patch.done_at = nowIso()
    const task = read(`/tasks/${id}`, new URLSearchParams()) as Row
    Object.assign(task, patch)
    put(`/tasks/${id}`, task)
    for (const l of lists((p) => p === '/tasks')) for (const t of l) if (t.id === id) Object.assign(t, patch)
    return clone(task)
  }],
  ['POST', /^\/tasks\/(\d+)\/comments$/, (m, body) => {
    const id = Number(m[1])
    const u = me()
    const c: Row = { id: nextId(), author_id: u.id, author: u.full_name, at: nowIso(), text: body.text, file_url: null }
    const path = `/tasks/${id}/comments`
    const list = (exact(path, new URLSearchParams()) as Row[] | undefined) ?? []
    list.push(c)
    put(path, list)
    const task = exact(`/tasks/${id}`, new URLSearchParams()) as Row | undefined
    if (task) task.comments = Number(task.comments ?? 0) + 1
    for (const l of lists((p) => p === '/tasks')) for (const t of l) if (t.id === id) t.comments = Number(t.comments ?? 0) + 1
    return { id: c.id, at: c.at }
  }],

  // payments
  ['POST', /^\/payments\/quote$/, (_m, body) => quote(body)],
  ['POST', /^\/payments$/, (_m, body) => {
    const q = quote(body)
    const sid = Number(body.student_id)
    const student = exact(`/students/${sid}`, new URLSearchParams()) as Row | undefined
    const pay: Row = {
      id: nextId(), student_id: sid, branch_id: student?.branch_id ?? 1, level_id: body.level_id ?? student?.level_id ?? null,
      category: 'course', amount: q.to_pay, discount: q.discount, lessons: q.lessons, lesson_price: q.lesson_price, method: body.method,
      received_by: me().id, paid_at: nowIso(), refunded: 0, is_first: false, note: body.note ?? null,
      student_name: student?.full_name ?? null, student_lessons_left: null,
    }
    if (student) {
      const bal = student.balance as Row | undefined
      if (bal) {
        bal.lessons_paid = Number(bal.lessons_paid ?? 0) + q.lessons
        bal.lessons_left = Number(bal.lessons_left ?? 0) + q.lessons
        bal.money_balance = Number(bal.money_balance ?? 0) - q.money_balance_used
      }
      student.lessons_left = Number(student.lessons_left ?? 0) + q.lessons
      student.last_payment_at = pay.paid_at
      pay.student_lessons_left = student.lessons_left
    }
    for (const l of lists((p) => p === '/payments')) l.unshift({ ...pay })
    for (const l of lists((p) => p === `/students/${sid}/ledger`)) l.unshift({ id: nextId(), at: pay.paid_at, kind: 'payment', lessons: q.lessons, amount: q.to_pay, note: body.note ?? null })
    return clone(pay)
  }],

  // shell
  ['POST', /^\/notifications\/read-all$/, () => {
    for (const d of all('/notifications') as { unread?: number; items?: Row[] }[]) {
      if (!d) continue
      d.unread = 0
      for (const n of d.items ?? []) n.read = true
    }
    const c = exact('/counters', new URLSearchParams()) as Row | undefined
    if (c) c.notifications = 0
    return null
  }],
  ['POST', /^\/checkin$/, (_m, body) => {
    const v = { id: nextId(), in_at: nowIso(), out_at: null, branch_id: body.branch_id }
    put('/checkin/me', { ...(exact('/checkin/me', new URLSearchParams()) as Row | undefined), ...v })
    return { id: v.id, in_at: v.in_at }
  }],
  ['POST', /^\/checkout$/, () => {
    const cur = (exact('/checkin/me', new URLSearchParams()) as Row | undefined) ?? {}
    const v: Row = { ...cur, out_at: nowIso() }
    put('/checkin/me', v)
    return { in_at: v.in_at ?? nowIso(), out_at: v.out_at }
  }],
]

function token(): Json {
  return { access_token: 'demo-access-token', refresh_token: null, token_type: 'bearer', mfa_required: false, mfa_token: null, mfa_setup_required: false }
}

function quote(body: Json): { lessons: number; lesson_price: number; gross: number; discount: number; money_balance_used: number; to_pay: number } {
  const student = exact(`/students/${Number(body.student_id)}`, new URLSearchParams()) as Row | undefined
  const bal = (student?.balance ?? {}) as Row
  const lessons = Number(body.lessons) || 0
  const price = Number(bal.lesson_price) || 3500
  const gross = lessons * price
  const discount = Math.min(Number(body.discount) || 0, gross)
  const used = Math.max(0, Math.min(Number(bal.money_balance) || 0, gross - discount))
  return { lessons, lesson_price: price, gross, discount, money_balance_used: used, to_pay: gross - discount - used }
}

function moveLead(id: number, stageId: number, lostReason: string | null): unknown {
  let moved: Row | null = null
  for (const b of all('/crm/board') as { columns?: { stage: Row; total: number; leads: Row[] }[] }[]) {
    const cols = b?.columns ?? []
    const to = cols.find((c) => c.stage.id === stageId)
    for (const c of cols) {
      const i = c.leads.findIndex((l) => l.id === id)
      if (i < 0) continue
      const lead = c.leads.splice(i, 1)[0] as Row
      c.total = Math.max(0, c.total - 1)
      Object.assign(lead, { stage_id: stageId, stage_changed_at: nowIso(), lost_reason: lostReason, stale: false })
      if (to) {
        to.leads.unshift(lead)
        to.total++
      }
      moved = lead
    }
  }
  const d = exact(`/crm/leads/${id}`, new URLSearchParams()) as { lead?: Row; events?: Row[] } | undefined
  if (d?.lead) {
    Object.assign(d.lead, { stage_id: stageId, stage_changed_at: nowIso(), lost_reason: lostReason })
    d.events?.unshift({ id: nextId(), at: nowIso(), kind: 'stage', text: null, actor_id: me().id, meta: { to: stageId } })
    moved ??= d.lead
  }
  return clone(moved ?? { id, stage_id: stageId })
}

/** Anything without a handler: succeed, keep simple edits in memory, say it is a demo. */
function generic(method: string, pathname: string, body: Json | undefined): unknown {
  notice()
  if (method === 'DELETE') return null
  const existing = exact(pathname, new URLSearchParams())
  if ((method === 'PATCH' || method === 'PUT') && existing && typeof existing === 'object' && !Array.isArray(existing)) {
    merge(existing, body ?? {})
    return clone(existing)
  }
  return { id: nextId(), ok: true, status: 'ok', ...(body ?? {}) }
}

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms))

export async function demoRequest(method: string, path: string, opts: RequestOptions): Promise<unknown> {
  await delay(method === 'GET' ? 60 : 120) // a touch of latency so loading states look natural
  opts.signal?.throwIfAborted()
  const { pathname, q } = parse(path)
  const body = (opts.body instanceof FormData ? undefined : opts.body) as Json | undefined

  if (method === 'POST' && pathname === '/auth/login') {
    const phone = String(body?.phone ?? '')
    await useRole(DEMO_PHONES[phone] ?? role ?? 'owner')
  }
  if (!role && pathname !== '/auth/logout') throw new ApiError(401, '')

  if (method === 'GET') return read(pathname, q)
  for (const [m, re, fn] of handlers) {
    if (m !== method) continue
    const hit = re.exec(pathname)
    if (hit) return fn(hit, body ?? {})
  }
  return generic(method, pathname, body)
}

/** Restores the role picked earlier in this browser, if any. */
export async function demoRestore(): Promise<boolean> {
  const r = storedRole()
  if (!r) return false
  await useRole(r)
  return true
}

export function demoDownload(): void {
  useToastStore().show('Демо-версия: выгрузка в Excel недоступна', 'info', 3000)
}
