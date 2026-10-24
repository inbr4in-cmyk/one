import { computed, onMounted } from 'vue'
import { useRefsStore } from '@/stores/refs'

export interface TeacherOption {
  id: number
  name: string
  /** Branches the teacher works in */
  branchIds?: number[]
}

/** Teachers for pickers, from GET /staff-directory?role=teacher (open to all staff). */
export function useTeachers() {
  const refs = useRefsStore()
  onMounted(() => refs.loadStaff())
  return computed<TeacherOption[]>(() =>
    refs.teachers.map((x) => ({ id: x.id, name: x.full_name, branchIds: x.branch_ids })).sort((a, b) => a.name.localeCompare(b.name)),
  )
}
