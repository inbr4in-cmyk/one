<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { UiButton, UiCard, UiEmptyState, UiField, UiIcon, UiInput, UiModal, UiSkeleton, UiTabs, UiTextarea } from '@/components/ui'
import { workApi, type Course, type ProgressRow } from '@/api/staffwork'
import { adminApi, type Role } from '@/api/admin'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import { apiErr } from '@/utils/err'
import TestsPanel from '@/components/tests/TestsPanel.vue'

type Tab = 'courses' | 'progress' | 'tests'
const { t, te } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const toast = useToastStore()
const route = useRoute()
const tab = ref<Tab>('courses')
const tabs = computed(() => [
  { value: 'courses' as const, label: t('training.tab.courses') },
  ...(auth.can('training.progress') ? [{ value: 'progress' as const, label: t('training.tab.progress') }] : []),
  ...(auth.can('tests.view') ? [{ value: 'tests' as const, label: t('tests.tab') }] : []),
])
// Deep link (?tab=tests) only to a tab this user can see.
if (tabs.value.some((x) => x.value === route.query.tab)) tab.value = route.query.tab as Tab
const courses = ref<Course[] | null>(null)
const progress = ref<ProgressRow[] | null>(null)
const roles = ref<Role[]>([])
const creating = ref(false)
const form = reactive({ title: '', description: '', role_codes: [] as string[] })
const error = ref<string | null>(null)
const busy = ref(false)

onMounted(async () => {
  courses.value = await workApi.courses().catch(() => [])
  if (auth.can('training.edit') && auth.can('roles.view')) roles.value = (await adminApi.roles().catch(() => [])).filter((r) => !r.archived_at)
})
watch(tab, async (v) => {
  router.replace({ query: v === 'courses' ? {} : { tab: v } })
  if (v === 'progress' && !progress.value) progress.value = await workApi.progress().catch(() => [])
}, { immediate: true })
const pct = (c: { done: number; materials?: number; total?: number }) => {
  const total = c.materials ?? c.total ?? 0
  return total ? Math.round((c.done / total) * 100) : 0
}
const allCourses = computed(() => {
  const m = new Map<number, string>()
  for (const r of progress.value ?? []) for (const c of r.courses) m.set(c.course_id, c.title ?? `#${c.course_id}`)
  return [...m]
})
const cell = (r: ProgressRow, id: number) => r.courses.find((c) => c.course_id === id)
const roleName = (code: string) => roles.value.find((r) => r.code === code)?.name ?? (te(`roles.${code}`) ? t(`roles.${code}`) : code)
const toggle = (code: string) => (form.role_codes = form.role_codes.includes(code) ? form.role_codes.filter((c) => c !== code) : [...form.role_codes, code])

function openCreate() {
  Object.assign(form, { title: '', description: '', role_codes: [] })
  error.value = null
  creating.value = true
}
async function create() {
  error.value = form.title.trim().length < 3 ? t('training.titleRequired') : null
  if (error.value) return
  busy.value = true
  try {
    const r = await workApi.createCourse({ title: form.title.trim(), description: form.description.trim() || null, role_codes: form.role_codes })
    toast.ok(t('training.created'))
    creating.value = false
    router.push(`/training/${r.id}`)
  } catch (e) {
    error.value = apiErr(e) ?? t('errors.generic')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="ph">
    <div><h1>{{ t('nav.training') }}</h1><p>{{ t('training.subtitle') }}</p></div>
    <span class="sp" />
    <UiButton v-if="auth.can('training.edit') && tab === 'courses'" variant="primary" icon="plus" @click="openCreate">{{ t('training.new') }}</UiButton>
  </div>
  <div v-if="tabs.length > 1" class="toolbar"><UiTabs v-model="tab" :items="tabs" :label="t('nav.training')" /></div>

  <template v-if="tab === 'courses'">
    <div v-if="!courses" class="shop-grid"><div v-for="i in 3" :key="i" class="card card-pad"><UiSkeleton :lines="3" /></div></div>
    <UiEmptyState v-else-if="!courses.length" icon="learning-base" :title="t('training.empty')" />
    <div v-else class="course-grid">
      <RouterLink v-for="c in courses" :key="c.id" :to="`/training/${c.id}`" class="card course-card">
        <div class="shop-ico"><UiIcon name="learning-base" :size="24" /></div>
        <b>{{ c.title }}</b>
        <p v-if="c.description" class="muted m0 clamp2">{{ c.description }}</p>
        <div class="course-bar" role="progressbar" :aria-valuenow="pct(c)" aria-valuemin="0" aria-valuemax="100" :aria-label="t('training.progressOf', { title: c.title })"><i :style="{ width: `${pct(c)}%` }" /></div>
        <span class="muted" style="font-size: 12.5px">{{ t('training.doneOf', { done: c.done, total: c.materials }) }}<template v-if="c.role_codes.length"> · {{ c.role_codes.map(roleName).join(', ') }}</template></span>
      </RouterLink>
    </div>
  </template>

  <TestsPanel v-else-if="tab === 'tests'" />

  <UiCard v-else flush>
    <div v-if="!progress" class="card-pad"><UiSkeleton :lines="5" /></div>
    <UiEmptyState v-else-if="!progress.length" icon="learning-base" :title="t('training.noProgress')" />
    <div v-else class="scroll-x">
      <table class="tbl" :style="{ minWidth: `${260 + allCourses.length * 130}px` }">
        <thead><tr><th>{{ t('staff.name') }}</th><th v-for="[id, title] in allCourses" :key="id" class="r">{{ title }}</th></tr></thead>
        <tbody>
          <tr v-for="r in progress" :key="r.user_id">
            <td><b>{{ r.full_name }}</b><div class="muted" style="font-size: 12px">{{ r.position || '—' }}</div></td>
            <td v-for="[id] in allCourses" :key="id" class="r">
              <template v-if="cell(r, id)">
                <b class="num" :class="{ okc: pct(cell(r, id)!) === 100 }">{{ pct(cell(r, id)!) }}%</b>
                <div class="muted num" style="font-size: 12px">{{ cell(r, id)!.done }}/{{ cell(r, id)!.total }}</div>
              </template>
              <span v-else class="muted">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </UiCard>

  <UiModal v-model:open="creating" :title="t('training.newTitle')">
    <form id="course-form" class="stack" @submit.prevent="create">
      <UiInput v-model="form.title" :label="t('training.title')" :placeholder="t('training.titlePh')" :maxlength="255" />
      <UiTextarea v-model="form.description" :label="t('training.description')" :rows="3" :maxlength="8000" />
      <UiField v-if="roles.length" :label="t('training.forRoles')" :hint="t('training.forRolesHint')">
        <div class="chips-row">
          <button v-for="r in roles" :key="r.id" type="button" class="tgl" :aria-pressed="form.role_codes.includes(r.code)" @click="toggle(r.code)">{{ r.name }}</button>
        </div>
      </UiField>
      <p v-if="error" class="form-err" role="alert">{{ error }}</p>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton type="submit" form="course-form" variant="navy" :loading="busy">{{ t('training.create') }}</UiButton>
    </template>
  </UiModal>
</template>
