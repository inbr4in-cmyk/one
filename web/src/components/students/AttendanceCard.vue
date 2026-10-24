<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiCard, UiSkeleton } from '@/components/ui'
import type { AttendanceMark } from '@/api/students'
import { dmy } from '@/utils/dates'
import type { Locale } from '@/i18n'

/** Attendance dots (oldest → newest) from GET /students/{id}/attendance. */
const props = defineProps<{ marks: AttendanceMark[] | null }>()
const { t, locale } = useI18n()
const CLS = { present: 'p', late: 'l', absent: 'a', excused: 'f' } as const
const KEY = { present: 'p', late: 'l', absent: 'a', excused: 'e' } as const

const dots = computed(() => (props.marks ?? []).slice(0, 24).reverse())
const counted = computed(() => (props.marks ?? []).filter((m) => m.status !== 'excused'))
const rate = computed(() => {
  const n = counted.value.length
  return n ? Math.round((counted.value.filter((m) => m.status === 'present' || m.status === 'late').length / n) * 100) : null
})
const count = (s: AttendanceMark['status']) => dots.value.filter((m) => m.status === s).length
const title = (m: AttendanceMark) => `${dmy(m.at, locale.value as Locale)} · ${t(`students.att.${KEY[m.status]}`)}${m.grade ? ` · ${m.grade}` : ''}`
</script>

<template>
  <UiCard :title="t('students.att.title')">
    <template v-if="rate !== null" #actions><b class="num">{{ rate }}%</b></template>
    <UiSkeleton v-if="!marks" :lines="2" />
    <p v-else-if="!marks.length" class="muted m0">{{ t('students.att.none') }}</p>
    <template v-else>
      <div class="att-dots" role="list" :aria-label="t('students.att.hint')">
        <i v-for="m in dots" :key="m.lesson_id" role="listitem" :class="CLS[m.status]" :title="title(m)" :aria-label="title(m)" />
      </div>
      <div class="mini-leg">
        <span><i style="background: var(--ok)" />{{ t('students.att.p') }} · {{ count('present') }}</span>
        <span><i style="background: var(--warn)" />{{ t('students.att.l') }} · {{ count('late') }}</span>
        <span><i style="background: var(--red)" />{{ t('students.att.a') }} · {{ count('absent') }}</span>
        <span v-if="count('excused')"><i style="background: var(--grid)" />{{ t('students.att.e') }} · {{ count('excused') }}</span>
      </div>
    </template>
  </UiCard>
</template>
