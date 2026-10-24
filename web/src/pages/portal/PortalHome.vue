<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiCard, UiChip, UiIcon, UiSkeleton } from '@/components/ui'
import { portalApi, type PortalHomework, type PortalLesson } from '@/api/portal'
import { usePortalStore } from '@/stores/portal'
import { dayLabel, hm, isoDate } from '@/utils/dates'
import { num } from '@/utils/period'
import type { Locale } from '@/i18n'

const { t, locale } = useI18n()
const portal = usePortalStore()
const loc = computed(() => locale.value as Locale)
const child = computed(() => portal.child)
const lessons = ref<PortalLesson[] | null>(null)
const homework = ref<PortalHomework[]>([])
const rate = ref<number | null>(null)

watch(() => child.value?.id, async (id) => {
  lessons.value = null
  homework.value = []
  rate.value = null
  if (!id) return
  const [l, h, a] = await Promise.allSettled([
    portalApi.schedule(id, { start: isoDate(new Date()), days: 14 }),
    child.value?.blocked ? Promise.reject(new Error('blocked')) : portalApi.homework(id),
    child.value?.blocked ? Promise.reject(new Error('blocked')) : portalApi.attendance(id),
  ])
  lessons.value = l.status === 'fulfilled' ? l.value.filter((x) => new Date(x.ends_at) > new Date()).slice(0, 3) : []
  homework.value = h.status === 'fulfilled' ? h.value.filter((x) => x.status === 'assigned') : []
  rate.value = a.status === 'fulfilled' ? a.value.month.rate : null
}, { immediate: true })

const greeting = computed(() => {
  const h = new Date().getHours()
  return t(h < 12 ? 'dash.morning' : h < 18 ? 'dash.day' : 'dash.evening', { name: (portal.me?.full_name ?? '').split(' ')[0] })
})
const tiles = computed(() => [
  { to: '/portal/progress', icon: 'progress', label: t('portal.nav.progress') },
  { to: '/portal/payments', icon: 'wallet', label: t('portal.nav.payments') },
  { to: '/portal/coins', icon: 'coin', label: t('portal.nav.coins') },
  { to: '/portal/feedback', icon: 'flag', label: t('nav.feedback') },
])
</script>

<template>
  <template v-if="child">
    <section class="p-hero">
      <div>
        <div class="sub">{{ greeting }}</div>
        <h1>{{ portal.isParent ? child.full_name : t('portal.myStudy') }}</h1>
        <div class="sub">{{ [child.level, child.groups[0]?.name, child.branch.name].filter(Boolean).join(' · ') }}</div>
      </div>
      <div class="p-stats">
        <RouterLink to="/portal/payments" class="p-stat" :class="{ bad: child.lessons_left <= 0 }"><b class="num">{{ child.lessons_left }}</b><span>{{ t('portal.lessonsLeft') }}</span></RouterLink>
        <RouterLink to="/portal/coins" class="p-stat"><b class="num">{{ num(child.coins, loc) }}</b><span>{{ t('portal.coins') }}</span></RouterLink>
        <RouterLink to="/portal/progress" class="p-stat"><b class="num">{{ rate === null ? '—' : `${rate}%` }}</b><span>{{ t('portal.attendance') }}</span></RouterLink>
      </div>
    </section>

    <div v-if="child.debt && !child.blocked" class="alert" role="status">
      <UiIcon name="debt" :size="18" class="ico" />
      <div class="grow"><b>{{ t('portal.debtTitle') }}</b><span>{{ t('portal.debtText', { n: -child.lessons_left }) }}</span></div>
    </div>
    <div v-else-if="child.lessons_left > 0 && child.lessons_left <= 2" class="alert info" role="status">
      <UiIcon name="alert" :size="18" class="ico" />
      <div class="grow"><b>{{ t('portal.lowTitle', { n: child.lessons_left }) }}</b><span>{{ t('portal.lowText') }}</span></div>
    </div>

    <div class="p-sec">
      <UiCard v-if="!child.blocked" :title="t('portal.next')">
        <template #actions><RouterLink to="/portal/schedule" class="linkbtn" style="font-size: 13px">{{ t('portal.allSchedule') }}</RouterLink></template>
        <UiSkeleton v-if="!lessons" :lines="3" />
        <p v-else-if="!lessons.length" class="muted m0">{{ t('portal.noLessons') }}</p>
        <div v-for="l in lessons ?? []" :key="l.id" class="p-lesson" :class="{ cancelled: l.status === 'cancelled' }">
          <div class="p-when"><b>{{ hm(l.starts_at, loc) }}</b><span>{{ dayLabel(l.starts_at, loc, { weekday: 'short', day: 'numeric' }) }}</span></div>
          <div class="grow"><b>{{ l.topic || l.group || t('portal.lesson') }}</b><span>{{ [l.teacher, l.room].filter(Boolean).join(' · ') }}</span></div>
          <UiChip v-if="l.status === 'cancelled'" tone="red" small>{{ t('portal.cancelled') }}</UiChip>
        </div>
      </UiCard>

      <RouterLink v-if="homework.length" to="/portal/homework" class="alert info" style="text-decoration: none; color: inherit">
        <UiIcon name="homework" :size="18" class="ico" />
        <div class="grow"><b>{{ t('portal.hwDue', { n: homework.length }) }}</b><span>{{ homework[0]?.title }}</span></div>
        <UiIcon name="arrow" :size="16" />
      </RouterLink>

      <div class="p-tiles">
        <RouterLink v-for="tl in tiles" :key="tl.to" :to="tl.to" class="p-tile"><UiIcon :name="tl.icon" :size="20" />{{ tl.label }}</RouterLink>
      </div>

      <UiCard v-if="child.groups.length" :title="t('portal.groups')">
        <div v-for="g in child.groups" :key="g.id" class="list-row">
          <div class="grow"><b>{{ g.name }}</b><span>{{ [g.level, g.teacher].filter(Boolean).join(' · ') }}</span></div>
          <RouterLink v-if="g.chat_id && !child.blocked" :to="`/portal/chats/${g.chat_id}`" class="btn sm"><UiIcon name="chat" :size="16" />{{ t('portal.groupChat') }}</RouterLink>
        </div>
      </UiCard>

      <UiCard :title="t('portal.branch')">
        <div class="list-row" style="padding: 0">
          <div class="grow"><b>{{ child.branch.name }}</b><span>{{ child.branch.address || '—' }}</span></div>
          <a v-if="child.branch.phone" :href="`tel:${child.branch.phone}`" class="btn sm"><UiIcon name="phone" :size="16" />{{ t('portal.call') }}</a>
        </div>
      </UiCard>
    </div>
  </template>
</template>
