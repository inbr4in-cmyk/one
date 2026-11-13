<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { UiButton, UiChip, UiEmptyState, UiIcon, UiInput, UiSkeleton } from '@/components/ui'
import { academicsApi, type Lesson } from '@/api/academics'
import { useBranchStore } from '@/stores/branch'
import { useRefsStore } from '@/stores/refs'
import { addDays, dayLabel, hm, isoDate, parseDate, schoolNow } from '@/utils/dates'
import { tone } from '@/utils/levels'
import type { Locale } from '@/i18n'

/** Lessons of a day; the current one is highlighted. Opening one shows the sheet. */
const { t, locale } = useI18n()
const router = useRouter()
const branch = useBranchStore()
const refs = useRefsStore()
const loc = computed(() => locale.value as Locale)
const date = ref(isoDate(schoolNow()))
const lessons = ref<Lesson[]>([])
const loading = ref(true)

async function load() {
  loading.value = true
  try {
    lessons.value = await academicsApi.lessons({ from: date.value, to: date.value, branch_id: branch.filterId })
  } catch {
    lessons.value = []
  } finally {
    loading.value = false
  }
}
watch([date, () => branch.filterId], load)
onMounted(load)

const now = Date.now()
const live = (l: Lesson) => new Date(l.starts_at).getTime() - 15 * 60000 <= now && now < new Date(l.ends_at).getTime()
const state = (l: Lesson) => {
  if (l.attendance_marked_at) return { tone: 'ok' as const, text: t('attendance.marked') }
  if (live(l)) return { tone: 'ok' as const, text: t('attendance.live', { n: Math.max(0, Math.round((now - new Date(l.starts_at).getTime()) / 60000)) }) }
  if (new Date(l.starts_at).getTime() < now) return { tone: 'warn' as const, text: t('attendance.notMarked') }
  return { tone: undefined, text: t('attendance.upcoming') }
}
const shift = (n: number) => (date.value = isoDate(addDays(parseDate(date.value), n)))
const isToday = computed(() => date.value === isoDate(schoolNow()))
</script>

<template>
  <div class="ph">
    <div><h1>{{ t('attendance.title') }}</h1><p>{{ t('attendance.subtitle') }}</p></div>
  </div>
  <div class="toolbar">
    <UiButton size="sm" icon="arrow" class="flip" :aria-label="t('attendance.prevDay')" @click="shift(-1)" />
    <UiInput v-model="date" type="date" class="tb-date" :aria-label="t('schedule.date')" />
    <UiButton size="sm" icon="arrow" :aria-label="t('attendance.nextDay')" @click="shift(1)" />
    <UiButton v-if="!isToday" size="sm" variant="ghost" @click="date = isoDate(schoolNow())">{{ t('schedule.today') }}</UiButton>
    <span class="muted">{{ dayLabel(parseDate(date), loc, { weekday: 'long', day: 'numeric', month: 'long' }) }}</span>
  </div>

  <div v-if="loading" class="grid lesson-cards"><div v-for="i in 3" :key="i" class="card" style="padding: 16px"><UiSkeleton :lines="2" /></div></div>
  <div v-else-if="lessons.length" class="grid lesson-cards stagger">
    <button v-for="l in lessons" :key="l.id" type="button" class="card lesson-card" :class="{ live: live(l) }" @click="router.push(`/attendance/${l.id}`)">
      <span class="gav" :style="{ '--c': tone(refs.level(l.level_id)?.color) }">{{ (l.group_name ?? '·').slice(0, 2) }}</span>
      <span class="grow">
        <b>{{ l.group_name ?? (l.kind === 'support' ? 'Support · ' + (l.topic ?? '') : t('schedule.individual')) }}</b>
        <small class="num">{{ hm(l.starts_at, loc) }}–{{ hm(l.ends_at, loc) }} · {{ l.room_name }} · {{ l.teacher_name }}</small>
      </span>
      <UiChip v-if="l.trials" tone="red" small icon="flag">{{ l.trials }}</UiChip>
      <UiChip :tone="state(l).tone" small>{{ state(l).text }}</UiChip>
      <UiIcon name="arrow" :size="18" class="muted" />
    </button>
  </div>
  <UiEmptyState v-else large icon="check" :title="t('attendance.noLessons')" :text="t('attendance.noLessonsText')" />
</template>
