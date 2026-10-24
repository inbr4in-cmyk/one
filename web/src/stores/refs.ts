import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { orgApi, type Branch, type DirectoryEntry, type Level, type Room } from '@/api/org'

/** Reference data shared by many screens: branches, levels, rooms per branch, the staff directory. Loaded once. */
export const useRefsStore = defineStore('refs', () => {
  const branches = ref<Branch[]>([])
  const levels = ref<Level[]>([])
  const rooms = ref<Record<number, Room[]>>({})
  const staff = ref<DirectoryEntry[]>([])
  let loaded: Promise<void> | null = null
  let staffLoaded: Promise<void> | null = null

  const levelById = computed(() => new Map(levels.value.map((l) => [l.id, l])))
  const branchById = computed(() => new Map(branches.value.map((b) => [b.id, b])))
  const allRooms = computed(() => Object.values(rooms.value).flat())
  const teachers = computed(() => staff.value.filter((x) => x.roles.includes('teacher')))
  const staffById = computed(() => new Map(staff.value.map((x) => [x.id, x])))

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

  /** Colleagues for pickers (teachers, task assignees, payroll); any staff member may read the directory. */
  function loadStaff(): Promise<void> {
    if (!staffLoaded) {
      staffLoaded = orgApi.directory().then((r) => void (staff.value = r), () => void (staffLoaded = null))
    }
    return staffLoaded
  }

  function reset() {
    loaded = staffLoaded = null
    branches.value = []
    levels.value = []
    rooms.value = {}
    staff.value = []
  }

  const branchName = (id: number | null | undefined) => (id ? branchById.value.get(id)?.name ?? `#${id}` : '')
  const level = (id: number | null | undefined) => (id ? levelById.value.get(id) : undefined)

  const staffName = (id: number | null | undefined) => (id ? staffById.value.get(id)?.full_name ?? `#${id}` : '')

  return { branches, levels, rooms, staff, teachers, allRooms, levelById, staffById, load, roomsOf, loadStaff, reset, branchName, level, staffName }
})
