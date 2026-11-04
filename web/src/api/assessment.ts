import { http } from './http'

/** Test builder (backend/app/modules/assessment/router.py) and the public QR placement test. */
export type TestKind = 'placement' | 'final' | 'training'
export type QuestionKind = 'single' | 'multi' | 'text'

export interface ScaleRow {
  min: number
  level_id: number | null
}

export interface Test {
  id: number
  kind: TestKind
  title: string
  level_id: number | null
  max_score: number
  pass_score: number | null
  time_limit_min: number | null
  scale: ScaleRow[] | Record<string, unknown>
  is_published: boolean
  questions: number
}

export type TestIn = Omit<Test, 'id' | 'questions' | 'scale'> & { scale: ScaleRow[] }

export interface Question {
  id: number
  order: number
  kind: QuestionKind
  text: string
  options: string[]
  correct: number[]
  points: number
}

export type QuestionIn = Omit<Question, 'id'>

export const testsApi = {
  list: (kind?: TestKind) => http.get<Test[]>(`/tests${kind ? `?kind=${kind}` : ''}`),
  create: (body: TestIn) => http.post<Test>('/tests', body),
  update: (id: number, body: TestIn) => http.put<Test>(`/tests/${id}`, body),
  questions: (id: number) => http.get<Question[]>(`/tests/${id}/questions`),
  addQuestion: (testId: number, body: QuestionIn) => http.post<Question>(`/tests/${testId}/questions`, body, { silent: true }),
  updateQuestion: (id: number, body: QuestionIn) => http.put<Question>(`/questions/${id}`, body, { silent: true }),
  archiveQuestion: (id: number) => http.post<void>(`/questions/${id}/archive`),
  branchQr: (branchId: number) => http.get<{ token: string; path: string }>(`/branches/${branchId}/qr`),
}

/* ---------- public, no login ---------- */
export interface PublicQuestion {
  id: number
  kind: QuestionKind
  text: string
  options: string[]
}

export interface PublicTest {
  branch: string
  title: string
  time_limit_min: number | null
  questions: PublicQuestion[]
}

export interface StartIn {
  name: string
  phone: string
  age: number | null
  parent_name: string | null
  parent_phone: string | null
  consent: boolean
}

/**
 * Answers as the router's `score()` reads them: `{ "<question id>": [option indexes] | "free text" }`.
 * Single choice sends a one-element list.
 */
export type Answers = Record<string, number[] | string>

export interface PlacementResult {
  score: number
  max: number
  level: string | null
}

const pub = { auth: false, silent: true } as const

export const placementApi = {
  get: (token: string) => http.get<PublicTest>(`/public/placement/${encodeURIComponent(token)}`, pub),
  start: (token: string, body: StartIn) =>
    http.post<{ attempt_id: number; attempt_token: string }>(`/public/placement/${encodeURIComponent(token)}/start`, body, pub),
  submit: (attemptToken: string, answers: Answers) =>
    http.post<PlacementResult>('/public/placement/submit', { attempt_token: attemptToken, answers }, pub),
}
