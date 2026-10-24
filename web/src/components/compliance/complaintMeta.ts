import type { ComplaintStatus } from '@/api/compliance'

export const COMPLAINT_TONE: Record<ComplaintStatus, 'ok' | 'warn' | 'red' | 'info' | undefined> = {
  new: 'red', acknowledged: 'warn', investigating: 'info', answered: 'ok', closed: undefined, appealed: 'red',
}

/** Next handler actions for a complaint (the server checks permissions and the appeal rule again). */
export function complaintActions(status: ComplaintStatus, isOwner: boolean): ('acknowledge' | 'investigate' | 'answer' | 'close')[] {
  if (status === 'appealed') return isOwner ? ['answer', 'close'] : []
  if (status === 'new') return ['acknowledge', 'investigate', 'answer']
  if (status === 'acknowledged') return ['investigate', 'answer']
  if (status === 'investigating') return ['answer']
  if (status === 'answered') return ['close']
  return []
}
