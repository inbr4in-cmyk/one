<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiChip, UiField, UiIcon, UiInput, UiModal, UiSelect, UiTextarea } from '@/components/ui'
import LevelTag from '@/components/students/LevelTag.vue'
import { academicsApi, type Lesson } from '@/api/academics'
import type { Room } from '@/api/org'
import { ApiError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import type { TeacherOption } from '@/composables/useTeachers'
import { dayLabel, hm, isoDate } from '@/utils/dates'
import type { Locale } from '@/i18n'

/** Lesson details with cancel / move / substitute. Server conflicts (409) are shown in place. */
const props = defineProps<{ lesson: Lesson | null; teachers: TeacherOption[]; conflicts: string[] }>()
const emit = defineEmits<{ close: []; changed: [] }>()
const { t, locale } = useI18n()
const auth = useAuthStore()
const refs = useRefsStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)

type Mode = 'view' | 'cancel' | 'move' | 'sub' | 'delete'
const mode = ref<Mode>('view')
const error = ref<string | null>(null)
const busy = ref(false)
const rooms = ref<Room[]>([])
const form = reactive({ reason: '', date: '', start: '', end: '', room_id: 0, teacher_id: 0 })

const open = computed({ get: () => props.lesson !== null, set: (v) => !v && emit('close') })
const l = computed(() => props.lesson)
/** «Удалить урок»: admins only, for a lesson created by mistake (no marks yet). */
const canDelete = computed(() => auth.can('students.archive') && !l.value?.attendance_marked_at)
const canEdit = computed(() => auth.can('schedule.edit') && l.value?.status === 'planned')
const past = computed(() => (l.value ? new Date(l.value.ends_at) < new Date() : false))
const roomOptions = computed(() => rooms.value.filter((r) => r.status === 'active').map((r) => ({ value: r.id, label: r.name })))
const teacherOptions = computed(() => props.teachers.filter((x) => !l.value || !x.branchIds?.length || x.branchIds.includes(l.value.branch_id)).map((x) => ({ value: x.id, label: x.name })))
const hhmm = (iso: string) => {
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

watch(() => props.lesson, async (x) => {
  mode.value = 'view'
  error.value = null
  if (!x) return
  rooms.value = await refs.roomsOf(x.branch_id)
})

function start(m: Mode) {
  const x = l.value
  if (!x) return
  error.value = null
  Object.assign(form, {
    reason: '', date: isoDate(new Date(x.starts_at)), start: hhmm(x.starts_at), end: hhmm(x.ends_at), room_id: x.room_id,
    teacher_id: x.actual_teacher_id ?? x.teacher_id,
  })
  mode.value = m
}

async function submit() {
  const x = l.value
  if (!x) return
  error.value = null
  if (mode.value === 'delete') {
    busy.value = true
    try {
      await academicsApi.deleteLesson(x.id)
      toast.ok(t('schedule.deletedToast'))
      emit('changed')
      emit('close')
    } catch (e) {
      error.value = e instanceof ApiError ? e.detail || t('errors.generic') : t('errors.generic')
    } finally {
      busy.value = false
    }
    return
  }
  if ((mode.value === 'cancel' || mode.value === 'move') && form.reason.trim().length < 3) {
    error.value = t('common.reasonRequired')
    return
  }
  busy.value = true
  try {
    if (mode.value === 'cancel') {
      await academicsApi.cancel(x.id, form.reason.trim())
      toast.ok(t('schedule.cancelledToast'))
    } else if (mode.value === 'move') {
      if (form.end <= form.start) throw new ApiError(400, t('groups.rule.badTime'))
      await academicsApi.move(x.id, {
        starts_at: new Date(`${form.date}T${form.start}`).toISOString(),
        ends_at: new Date(`${form.date}T${form.end}`).toISOString(),
        room_id: form.room_id || null,
        reason: form.reason.trim(),
      })
      toast.ok(t('schedule.movedToast'))
    } else if (mode.value === 'sub') {
      await academicsApi.substitute(x.id, form.teacher_id)
      toast.ok(t('schedule.subToast'))
    }
    emit('changed')
    emit('close')
  } catch (e) {
    error.value = e instanceof ApiError ? e.detail || t('errors.generic') : t('errors.generic')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiModal v-model:open="open" :title="l ? (l.group_name ?? (l.kind === 'support' ? 'Support · ' + (l.topic ?? '') : t('schedule.individual'))) : ''">
    <template v-if="l">
      <div class="stack">
        <div class="lsn-meta">
          <div><UiIcon name="cal" :size="18" /><b class="num">{{ dayLabel(l.starts_at, loc, { weekday: 'long', day: 'numeric', month: 'long' }) }}, {{ hm(l.starts_at, loc) }}–{{ hm(l.ends_at, loc) }}</b></div>
          <div><UiIcon name="door" :size="18" />{{ l.room_name ?? '—' }}</div>
          <div><UiIcon name="user" :size="18" />{{ l.teacher_name ?? '—' }}<UiChip v-if="l.actual_teacher_id" tone="info" small>{{ t('schedule.sub') }}</UiChip></div>
          <div v-if="l.level_id"><UiIcon name="level" :size="18" /><LevelTag :id="l.level_id" full /></div>
          <div v-if="l.trials"><UiIcon name="flag" :size="18" />{{ t('schedule.trials', { n: l.trials }) }}</div>
        </div>
        <UiChip v-if="l.status === 'cancelled'" tone="red">{{ t('schedule.cancelled') }}<template v-if="l.cancel_reason"> · {{ l.cancel_reason }}</template></UiChip>
        <div v-if="conflicts.length" class="alert red" role="alert">
          <UiIcon name="alert" />
          <div class="grow"><b>{{ t('schedule.conflict') }}</b><span v-for="(c, i) in conflicts" :key="i" style="display: block">{{ c }}</span></div>
        </div>

        <Transition name="swap" mode="out-in">
          <form v-if="mode !== 'view'" :key="mode" id="lsn-form" class="stack" @submit.prevent="submit">
            <template v-if="mode === 'move'">
              <div class="form-3">
                <UiInput v-model="form.date" type="date" :label="t('schedule.date')" />
                <UiInput v-model="form.start" type="time" :label="t('groups.rule.start')" />
                <UiInput v-model="form.end" type="time" :label="t('groups.rule.end2')" />
              </div>
              <UiField :label="t('groups.room')"><UiSelect v-model="form.room_id" :options="roomOptions" :label="t('groups.room')" block /></UiField>
            </template>
            <UiField v-if="mode === 'sub'" :label="t('schedule.subTeacher')">
              <UiSelect v-model="form.teacher_id" :options="teacherOptions" :label="t('schedule.subTeacher')" block />
            </UiField>
            <p v-if="mode === 'delete'" class="m0">{{ t('schedule.deleteText') }}</p>
            <UiTextarea v-if="mode === 'cancel' || mode === 'move'" v-model="form.reason" :label="t('common.reason')" :rows="2" />
          </form>
        </Transition>
        <div v-if="error" class="alert red" role="alert"><UiIcon name="alert" /><div class="grow"><b>{{ error }}</b></div></div>
      </div>
    </template>
    <template #footer="{ close }">
      <template v-if="l && mode === 'view'">
        <UiButton v-if="auth.can('attendance.view') && l.status !== 'cancelled'" :to="`/attendance/${l.id}`" icon="check">{{ t('nav.attendance') }}</UiButton>
        <UiButton v-if="canDelete" variant="ghost" danger icon="delete" @click="start('delete')">{{ t('schedule.delete') }}</UiButton>
        <span class="sp" />
        <template v-if="canEdit && !past">
          <UiButton variant="ghost" @click="start('sub')">{{ t('schedule.substitute') }}</UiButton>
          <UiButton variant="ghost" @click="start('move')">{{ t('schedule.move') }}</UiButton>
          <UiButton variant="ghost" danger @click="start('cancel')">{{ t('schedule.cancel') }}</UiButton>
        </template>
        <UiButton v-else @click="close">{{ t('common.close') }}</UiButton>
      </template>
      <template v-else>
        <UiButton @click="mode = 'view'">{{ t('common.back') }}</UiButton>
        <UiButton :variant="mode === 'cancel' || mode === 'delete' ? 'primary' : 'navy'" type="submit" form="lsn-form" :loading="busy">
          {{ mode === 'delete' ? t('schedule.delete') : mode === 'cancel' ? t('schedule.cancelConfirm') : mode === 'move' ? t('schedule.moveConfirm') : t('schedule.subConfirm') }}
        </UiButton>
      </template>
    </template>
  </UiModal>
</template>
