import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { orgApi, type Branch, type Level, type Room, type StaffMember } from '@/api/org'
import { useAuthStore } from './auth'

/** Reference data shared by many screens: branches, levels, rooms per branch, teachers. Loaded once. */
export const useRefsStore = defineStore('refs', () => {
  const branches = ref<Branch[]>([])
  const levels = ref<Level[]>([])
  const rooms = ref<Record<number, Room[]>>({})
  const teachers = ref<StaffMember[]>([])
  let loaded: Promise<void> | null = null
  let teachersLoaded: Promise<void> | null = null

  const levelById = computed(() => new Map(levels.value.map((l) => [l.id, l])))
  const branchById = computed(() => new Map(branches.value.map((b) => [b.id, b])))
  const allRooms = computed(() => Object.values(rooms.value).flat())

  function load(): Promise<void> {
    if (!loaded) {
      loaded = (async () => {
        const [b, l] = await Promise.allSettled([orgApi.branches(), orgApi.levels()])
        if (b.status === 'fulfilled') branches.value = b.value
        if (l.status === 'fulfilled') levels.value = l.value
      })()
    }
    return loaded
  }

  async function roomsOf(branchId: number): Promise<Room[]> {
    if (!rooms.value[branchId]) {
      try {
        rooms.value = { ...rooms.value, [branchId]: await orgApi.rooms(branchId) }
      } catch {
        return []
      }
    }
    return rooms.value[branchId] ?? []
  }

  /** Teachers need staff.view; without it the list stays empty and pickers fall back to what screens know. */
  function loadTeachers(): Promise<void> {
    if (!teachersLoaded) {
      teachersLoaded = (async () => {
        if (!useAuthStore().can('staff.view')) return
        try {
          teachers.value = (await orgApi.staff({ role: 'teacher' })).items
        } catch {
          /* no access */
        }
      })()
    }
    return teachersLoaded
  }

  function reset() {
    loaded = teachersLoaded = null
    branches.value = []
    levels.value = []
    rooms.value = {}
    teachers.value = []
  }

  const branchName = (id: number | null | undefined) => (id ? branchById.value.get(id)?.name ?? `#${id}` : '')
  const level = (id: number | null | undefined) => (id ? levelById.value.get(id) : undefined)

  return { branches, levels, rooms, teachers, allRooms, levelById, load, roomsOf, loadTeachers, reset, branchName, level }
})
