import { computed, onMounted, type Ref } from 'vue'
import { useRefsStore } from '@/stores/refs'

export interface TeacherOption {
  id: number
  name: string
  /** Branches the teacher works in, when known */
  branchIds?: number[]
}

/**
 * Teachers for pickers. The staff directory needs `staff.view`; without it we fall back to the
 * teachers the screen already knows from groups and lessons.
 */
export function useTeachers(known: Ref<{ teacher_id: number; teacher_name: string | null; branch_id?: number }[]>) {
  const refs = useRefsStore()
  onMounted(() => refs.loadTeachers())
  return computed<TeacherOption[]>(() => {
    const map = new Map<number, TeacherOption>()
    refs.teachers.filter((x) => x.is_active).forEach((x) => map.set(x.id, { id: x.id, name: x.full_name, branchIds: x.branch_ids }))
    for (const x of known.value) {
      if (!x.teacher_name || refs.teachers.some((s) => s.id === x.teacher_id)) continue
      const cur = map.get(x.teacher_id) ?? { id: x.teacher_id, name: x.teacher_name, branchIds: [] }
      if (x.branch_id && !cur.branchIds!.includes(x.branch_id)) cur.branchIds!.push(x.branch_id)
      map.set(x.teacher_id, cur)
    }
    return [...map.values()].sort((a, b) => a.name.localeCompare(b.name))
  })
}
