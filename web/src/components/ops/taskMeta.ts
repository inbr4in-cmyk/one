import type { Task, TaskLink } from '@/api/tasks'

/** Where a task's link leads in the staff app. */
export function linkRoute(type: TaskLink | null, id: number | null): string | { path: string; query: Record<string, string> } | null {
  if (!type || !id) return null
  if (type === 'student') return `/students/${id}`
  if (type === 'group') return `/groups/${id}`
  if (type === 'lesson') return `/attendance/${id}`
  return { path: '/crm', query: { lead: String(id) } }
}

export const STATUS_TONE: Record<Task['status'], 'ok' | 'warn' | 'red' | 'info' | undefined> = {
  new: 'info', in_progress: 'warn', review: 'info', done: 'ok', cancelled: undefined,
}

/** Status moves the server allows: an assignee goes forward (and back from review); the author may set anything. */
export function nextStatuses(task: Task, me: number, isAuthor: boolean): Task['status'][] {
  if (isAuthor) return (['new', 'in_progress', 'review', 'done', 'cancelled'] as const).filter((s) => s !== task.status)
  if (!task.assignees.some((a) => a.id === me)) return []
  const moves: Partial<Record<Task['status'], Task['status'][]>> = { new: ['in_progress', 'review', 'done'], in_progress: ['review', 'done'], review: ['in_progress'] }
  return moves[task.status] ?? []
}
