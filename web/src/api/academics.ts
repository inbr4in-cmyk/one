import { http, qs } from './http'

export interface ScheduleRuleRef {
  id: number
  weekdays: number[]
  start: string
  end: string
  room_id: number
}

export interface Group {
  id: number
  name: string
  branch_id: number
  /** empty for an open lesson (kind «club») */
  level_id: number | null
  teacher_id: number
  room_id: number | null
  capacity: number
  starts_on: string | null
  status: 'recruiting' | 'active' | 'finished'
  /** group | duo (2 students) | individual (1 student) */
  kind?: CourseKind
  chat_id: number | null
  members: number
  teacher_name: string | null
  schedule: ScheduleRuleRef[]
}

export type CourseKind = 'group' | 'duo' | 'individual' | 'club'
export const COURSE_KINDS: CourseKind[] = ['group', 'duo', 'individual', 'club']
/** Sprite icon per format: one person, two people, a group */
export type LessonKind = CourseKind | 'support'
export const KIND_ICON: Record<LessonKind, string> = { individual: 'user', duo: 'users', group: 'groups', club: 'speaking', support: 'idea' }

export interface GroupIn {
  name: string
  branch_id: number
  level_id: number | null
  teacher_id: number
  room_id: number | null
  capacity: number
  starts_on: string | null
  status: Group['status']
  kind?: CourseKind
}

export interface GroupMember {
  student_id: number
  full_name: string
  joined_on: string
  lessons_left: number
  status: string
}

export interface RuleIn {
  weekdays: number[]
  start_time: string
  end_time: string
  room_id: number
  valid_from: string
  valid_to?: string | null
}

export interface Lesson {
  id: number
  branch_id: number
  group_id: number | null
  student_id: number | null
  level_id: number | null
  teacher_id: number
  actual_teacher_id: number | null
  room_id: number
  starts_at: string
  ends_at: string
  status: 'planned' | 'done' | 'cancelled'
  cancel_reason: string | null
  attendance_marked_at: string | null
  topic: string | null
  group_name: string | null
  kind?: LessonKind
  teacher_name: string | null
  room_name: string | null
  trials: number
}

export type AttendanceStatus = 'present' | 'late' | 'absent' | 'excused'

export interface RosterRow {
  student_id: number | null
  lead_id: number | null
  full_name: string
  is_trial: boolean
  status: AttendanceStatus | null
  grade: number | null
  comment: string | null
  stars: number
  lessons_left: number | null
  frozen: boolean
  blocked: boolean
}

export interface Roster {
  lesson: Lesson
  can_edit: boolean
  needs_reason: boolean
  rows: RosterRow[]
}

export interface MarkIn {
  student_id: number | null
  lead_id: number | null
  status: AttendanceStatus
  grade: number | null
  comment: string | null
  stars: number
}

export interface Homework {
  id: number
  group_id: number
  lesson_id: number | null
  title: string
  body: string | null
  due_at: string | null
  created_at: string
  submitted: number
  checked: number
}

export interface HomeworkIn {
  title: string
  body: string | null
  due_at: string | null
  lesson_id: number | null
}

export type SubmissionStatus = 'assigned' | 'submitted' | 'checked'

export interface HomeworkSubmission {
  student_id: number
  full_name: string
  status: SubmissionStatus
  answer: string | null
  file_url: string | null
  grade: number | null
  teacher_comment: string | null
  submitted_at: string | null
}

export interface LessonQuery {
  from: string
  to: string
  branch_id?: number | null
  room_id?: number | null
  teacher_id?: number | null
  group_id?: number | null
  include_cancelled?: boolean
}

export const academicsApi = {
  groups: (p: { branch_id?: number | null; level_id?: number | null; teacher_id?: number | null } = {}) =>
    http.get<Group[]>(`/groups${qs(p)}`),
  group: (id: number) => http.get<Group>(`/groups/${id}`),
  createGroup: (body: GroupIn) => http.post<Group>('/groups', body),
  updateGroup: (id: number, body: GroupIn) => http.patch<Group>(`/groups/${id}`, body),
  archiveGroup: (id: number) => http.post<null>(`/groups/${id}/archive`),
  members: (id: number) => http.get<GroupMember[]>(`/groups/${id}/members`),
  addMember: (id: number, student_id: number) => http.post<{ ok: boolean }>(`/groups/${id}/members`, { student_id }),
  removeMember: (id: number, studentId: number) => http.delete(`/groups/${id}/members/${studentId}`),
  addRule: (id: number, body: RuleIn) =>
    http.post<{ rule_id: number; created: number; conflicts: string[] }>(`/groups/${id}/schedule`, body, { silent: true }),
  endRule: (ruleId: number) => http.delete(`/schedule-rules/${ruleId}`),
  lessons: (q: LessonQuery) => http.get<Lesson[]>(`/lessons${qs({ ...q })}`),
  createLesson: (body: { group_id?: number | null; student_id?: number | null; teacher_id: number; room_id: number; starts_at: string; ends_at: string; topic?: string | null; support?: boolean }) =>
    http.post<Lesson>('/lessons', body, { silent: true }),
  cancel: (id: number, reason: string) => http.post<Lesson>(`/lessons/${id}/cancel`, { reason }),
  backfill: (body: { date_from: string; date_to: string; branch_id?: number | null; members_from_start: boolean }) =>
    http.post<{ created: number; groups: number; members: number; conflicts: string[] }>('/schedule/backfill', body, { silent: true }),
  deleteLesson: (id: number) => http.delete<void>(`/lessons/${id}`, { silent: true }),
  move: (id: number, body: { starts_at: string; ends_at: string; room_id?: number | null; reason: string }) =>
    http.post<Lesson>(`/lessons/${id}/move`, body, { silent: true }),
  substitute: (id: number, teacher_id: number) => http.post<Lesson>(`/lessons/${id}/substitute`, { teacher_id }, { silent: true }),
  roster: (lessonId: number) => http.get<Roster>(`/lessons/${lessonId}/attendance`),
  mark: (lessonId: number, body: { marks: MarkIn[]; reason?: string | null; topic?: string | null }) =>
    http.put<Roster>(`/lessons/${lessonId}/attendance`, body),
  homework: (groupId: number) => http.get<Homework[]>(`/groups/${groupId}/homework`, { silent: true }),
  addHomework: (groupId: number, body: Partial<HomeworkIn> & { title: string }) =>
    http.post<Homework>(`/groups/${groupId}/homework`, body, { silent: true }),
  editHomework: (id: number, body: Partial<HomeworkIn>) => http.patch<Homework>(`/homework/${id}`, body, { silent: true }),
  archiveHomework: (id: number) => http.post<void>(`/homework/${id}/archive`),
  /** One row per active group member */
  submissions: (id: number) => http.get<HomeworkSubmission[]>(`/homework/${id}/submissions`),
  check: (id: number, studentId: number, body: { grade: number | null; comment: string | null }) =>
    http.put<void>(`/homework/${id}/submissions/${studentId}`, body, { silent: true }),
}
