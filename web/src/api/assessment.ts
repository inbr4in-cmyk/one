import { http, qs } from './http'

/** Test builder (backend/app/modules/assessment/router.py) and the public QR placement test. */
export type TestKind = 'placement' | 'progress' | 'final' | 'training'
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

/** «Оценка урока» by QR: staff make a link for a group's lesson, students answer without logging in. */
export interface SurveyQuestion {
  text: string
  kind: 'stars' | 'text'
}
export interface SurveyLink {
  token: string
  path: string
  lesson_id: number
  lesson: string
  group: string
  answers: number
}
export interface PublicSurvey {
  group: string | null
  teacher: string | null
  lesson: string
  open: boolean
  questions: SurveyQuestion[]
}
export interface SurveyResults {
  lessons: {
    survey_id: number
    lesson_id: number
    at: string
    group: string | null
    teacher: string | null
    answers: number
    avg: number | null
    questions: { text: string; kind: 'stars' | 'text'; avg?: number | null; count?: number; comments?: string[] }[]
  }[]
  teachers: { teacher_id: number; teacher: string | null; lessons: number; answers: number; avg: number | null }[]
}
export const surveyApi = {
  questions: () => http.get<SurveyQuestion[]>('/lesson-surveys/questions'),
  setQuestions: (questions: SurveyQuestion[]) => http.put<SurveyQuestion[]>('/lesson-surveys/questions', { questions }, { silent: true }),
  open: (group_id: number) => http.post<SurveyLink>('/lesson-surveys', { group_id }, { silent: true }),
  results: (p: { branch_id?: number | null } = {}) => http.get<SurveyResults>(`/lesson-surveys/results${qs(p)}`),
  get: (token: string) => http.get<PublicSurvey>(`/public/lesson-survey/${encodeURIComponent(token)}`, pub),
  answer: (token: string, answers: (number | string | null)[]) =>
    http.post<{ ok: boolean }>(`/public/lesson-survey/${encodeURIComponent(token)}`, { answers }, pub),
}

/* ---------- group tests: planned for a lesson, taken online (backend/app/modules/assessment/sessions.py) ---------- */
export interface TestSession {
  id: number
  test_id: number
  title: string
  kind: TestKind
  group_id: number
  group_name: string
  lesson_id: number | null
  lesson_at: string | null
  status: 'planned' | 'running' | 'finished'
  time_limit_min: number
  started_at: string | null
  ends_at: string | null
  finished_at: string | null
}

export interface SessionRow {
  student_id: number
  full_name: string
  has_login: boolean
  status: 'none' | 'in_progress' | 'void' | 'done' | 'needs_review'
  answered: number
  score: number | null
  duration_sec: number | null
  voided_at: string | null
  restores: number
  place: number | null
}

export interface SessionBoard extends TestSession {
  max_score: number
  questions: number
  now: string
  can_run: boolean
  rows: SessionRow[]
}

export const sessionsApi = {
  list: (p: { group_id?: number; active?: boolean } = {}) => http.get<TestSession[]>(`/test-sessions${qs(p)}`),
  plan: (body: { group_id: number; test_id: number; lesson_id: number }) => http.post<TestSession>('/test-sessions', body, { silent: true }),
  remove: (id: number) => http.delete<void>(`/test-sessions/${id}`),
  get: (id: number) => http.get<SessionBoard>(`/test-sessions/${id}`, { silent: true }),
  start: (id: number, time_limit_min: number) => http.post<SessionBoard>(`/test-sessions/${id}/start`, { time_limit_min }),
  finish: (id: number) => http.post<SessionBoard>(`/test-sessions/${id}/finish`),
  restore: (id: number, student_id: number) => http.post<SessionBoard>(`/test-sessions/${id}/restore`, { student_id }),
}

/** What the student sees while taking a group test: one question at a time, never the correct answers */
export interface MyTestState {
  id: number
  title: string
  status: 'planned' | 'running' | 'finished'
  ends_at: string | null
  now: string
  time_limit_min: number
  attempt: { status: 'in_progress' | 'void' | 'done' | 'needs_review'; position: number; total: number; score: number | null; max_score: number | null; duration_sec: number | null } | null
  question: PublicQuestion | null
}

export const myTestsApi = {
  list: (student_id: number) => http.get<{ id: number; title: string; status: string; ends_at: string | null; my_status: string | null }[]>(`/portal/tests?student_id=${student_id}`, { silent: true }),
  state: (id: number, student_id: number) => http.get<MyTestState>(`/portal/tests/${id}?student_id=${student_id}`, { silent: true }),
  begin: (id: number, student_id: number) => http.post<MyTestState>(`/portal/tests/${id}/begin`, { student_id }, { silent: true }),
  answer: (id: number, body: { student_id: number; question_id: number; answer: number[] | string }) => http.post<MyTestState>(`/portal/tests/${id}/answer`, body, { silent: true }),
  leave: (id: number, student_id: number) => http.post<MyTestState>(`/portal/tests/${id}/leave`, { student_id }, { silent: true, keepalive: true }),
}
