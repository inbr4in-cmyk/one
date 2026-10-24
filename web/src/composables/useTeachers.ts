import { computed, onMounted, type Ref } from 'vue'
import { useRefsStore } from '@/stores/refs'

export interface TeacherOption {
  id: number
  name: string
}

/**
 * Teachers for pickers. The staff directory needs `staff.view`; without it we fall back to the
 * teachers the screen already knows from groups and lessons.
 */
export function useTeachers(known: Ref<{ teacher_id: number; teacher_name: string | null }[]>) {
  const refs = useRefsStore()
  onMounted(() => refs.loadTeachers())
  return computed<TeacherOption[]>(() => {
    const map = new Map<number, string>()
    refs.teachers.filter((x) => x.is_active).forEach((x) => map.set(x.id, x.full_name))
    known.value.forEach((x) => x.teacher_name && !map.has(x.teacher_id) && map.set(x.teacher_id, x.teacher_name))
    return [...map].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name))
  })
}
