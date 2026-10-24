<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiCard, UiChip, UiEmptyState, UiSkeleton } from '@/components/ui'
import { portalApi, type PortalLesson } from '@/api/portal'
import { usePortalStore } from '@/stores/portal'
import { addDays, dayLabel, hm, isoDate, weekStart } from '@/utils/dates'
import type { Locale } from '@/i18n'

const DAYS = 14
const { t, locale } = useI18n()
const portal = usePortalStore()
const loc = computed(() => locale.value as Locale)
const start = ref(weekStart(new Date()))
const lessons = ref<PortalLesson[] | null>(null)

watch([() => portal.child?.id, start], async ([id]) => {
  lessons.value = null
  if (!id) return
  lessons.value = await portalApi.schedule(id, { start: isoDate(start.value), days: DAYS }).catch(() => [])
}, { immediate: true })

const days = computed(() => {
  const m = new Map<string, PortalLesson[]>()
  for (const l of lessons.value ?? []) {
    const k = isoDate(new Date(l.starts_at))
    m.set(k, [...(m.get(k) ?? []), l])
  }
  return [...m]
})
const today = isoDate(new Date())
const range = computed(() => `${dayLabel(start.value, loc.value, { day: 'numeric', month: 'short' })} — ${dayLabel(addDays(start.value, DAYS - 1), loc.value, { day: 'numeric', month: 'short' })}`)
const isPast = (l: PortalLesson) => new Date(l.ends_at) < new Date()
</script>

<template>
  <div class="ph"><div><h1>{{ t('portal.nav.schedule') }}</h1><p>{{ range }}</p></div></div>
  <div class="toolbar">
    <div class="period">
      <button type="button" class="btn sm tgl" :aria-label="t('common.prev')" @click="start = addDays(start, -DAYS)"><svg class="ico flip-ico" aria-hidden="true"><use href="#i-arrow" /></svg></button>
      <button type="button" class="btn sm tgl" @click="start = weekStart(new Date())">{{ t('portal.thisWeek') }}</button>
      <button type="button" class="btn sm tgl" :aria-label="t('common.next')" @click="start = addDays(start, DAYS)"><svg class="ico" aria-hidden="true"><use href="#i-arrow" /></svg></button>
    </div>
  </div>
  <UiCard>
    <UiSkeleton v-if="!lessons" :lines="6" />
    <UiEmptyState v-else-if="!days.length" icon="cal" :title="t('portal.noLessonsRange')" />
    <template v-for="[d, list] in days" :key="d">
      <div class="p-day">{{ d === today ? t('portal.today') : dayLabel(`${d}T12:00:00`, loc, { weekday: 'long', day: 'numeric', month: 'long' }) }}</div>
      <div v-for="l in list" :key="l.id" class="p-lesson" :class="{ cancelled: l.status === 'cancelled' }" :style="isPast(l) && l.status !== 'cancelled' ? 'opacity:.72' : undefined">
        <div class="p-when"><b>{{ hm(l.starts_at, loc) }}</b><span>{{ hm(l.ends_at, loc) }}</span></div>
        <div class="grow">
          <b>{{ l.group || t('portal.individual') }}</b>
          <span>{{ [l.teacher, l.room].filter(Boolean).join(' · ') }}<template v-if="l.topic"> · {{ l.topic }}</template></span>
          <span v-if="l.cancel_reason" class="redc" style="display: block">{{ l.cancel_reason }}</span>
        </div>
        <UiChip v-if="l.status === 'cancelled'" tone="red" small>{{ t('portal.cancelled') }}</UiChip>
        <UiChip v-else-if="l.status === 'done'" tone="ok" small>{{ t('portal.held') }}</UiChip>
      </div>
    </template>
  </UiCard>
</template>
