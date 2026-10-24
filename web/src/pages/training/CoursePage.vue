<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { UiButton, UiCard, UiChip, UiEmptyState, UiIcon, UiInput, UiModal, UiSegmented, UiSkeleton, UiTextarea } from '@/components/ui'
import DocBody from '@/components/compliance/DocBody.vue'
import { workApi, type CourseDetail, type Material } from '@/api/staffwork'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import { dmy } from '@/utils/dates'
import { apiErr } from '@/utils/err'
import { safeUrl } from '@/utils/url'
import type { Locale } from '@/i18n'

const { t, locale } = useI18n()
const route = useRoute()
const auth = useAuthStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)
const course = ref<CourseDetail | null>(null)
const notFound = ref(false)
const marking = ref<number | null>(null)
const expanded = ref<number | null>(null)
const adding = ref(false)
const form = reactive({ kind: 'video' as 'video' | 'document', title: '', url: '', body: '' })
const error = ref<string | null>(null)
const busy = ref(false)
const id = computed(() => Number(route.params.id))
const done = computed(() => course.value?.materials.filter((m) => m.done_at).length ?? 0)
const kinds = computed(() => (['video', 'document'] as const).map((k) => ({ value: k, label: t(`training.kind.${k}`) })))
const ICON: Record<Material['kind'], string> = { video: 'video', document: 'file', test: 'tests' }

async function load() {
  notFound.value = false
  try {
    course.value = await workApi.course(id.value)
  } catch {
    notFound.value = true
  }
}
watch(id, load, { immediate: true })

async function markDone(m: Material) {
  marking.value = m.id
  try {
    const r = await workApi.done(m.id)
    m.done_at = r.done_at
    toast.ok(t('training.marked'))
  } finally {
    marking.value = null
  }
}
function openAdd() {
  Object.assign(form, { kind: 'video', title: '', url: '', body: '' })
  error.value = null
  adding.value = true
}
async function add() {
  const url = form.url.trim()
  error.value = form.title.trim().length < 2 ? t('training.titleRequired') : url && !/^https?:\/\//.test(url) ? t('training.urlInvalid') : !url && !form.body.trim() ? t('training.contentRequired') : null
  if (error.value) return
  busy.value = true
  try {
    await workApi.addMaterial(id.value, { kind: form.kind, title: form.title.trim(), url: url || null, body: form.body.trim() || null, order: (course.value?.materials.length ?? 0) + 1 })
    toast.ok(t('training.added'))
    adding.value = false
    load()
  } catch (e) {
    error.value = apiErr(e) ?? t('errors.generic')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiEmptyState v-if="notFound" large icon="learning-base" :title="t('training.notFound')">
    <UiButton to="/training" icon="arrow">{{ t('nav.training') }}</UiButton>
  </UiEmptyState>
  <UiCard v-else-if="!course"><UiSkeleton :lines="6" /></UiCard>
  <template v-else>
    <nav class="crumbs" :aria-label="t('common.breadcrumbs')"><RouterLink to="/training">{{ t('nav.training') }}</RouterLink> / <span>{{ course.title }}</span></nav>
    <div class="ph">
      <div><h1>{{ course.title }}</h1><p>{{ t('training.doneOf', { done, total: course.materials.length }) }}</p></div>
      <span class="sp" />
      <UiButton v-if="auth.can('training.edit')" icon="plus" @click="openAdd">{{ t('training.addMaterial') }}</UiButton>
    </div>
    <p v-if="course.description" class="muted pre" style="margin-top: 0">{{ course.description }}</p>
    <UiCard>
      <UiEmptyState v-if="!course.materials.length" icon="file" :title="t('training.noMaterials')" />
      <div v-for="m in course.materials" :key="m.id" class="mat" :class="{ done: !!m.done_at }">
        <span class="mat-ico"><UiIcon :name="m.done_at ? 'ok' : ICON[m.kind]" :size="18" /></span>
        <div class="grow">
          <b>{{ m.title }}</b>
          <span class="muted" style="font-size: 12.5px">{{ t(`training.kind.${m.kind}`) }}<template v-if="m.done_at"> · {{ t('training.doneAt', { date: dmy(m.done_at, loc) }) }}</template><template v-if="m.score != null"> · {{ t('training.score', { n: m.score }) }}</template></span>
          <div class="chips-row">
            <a v-if="m.url && safeUrl(m.url)" class="btn sm" :href="m.url" target="_blank" rel="noopener noreferrer"><UiIcon name="eye" :size="16" />{{ t('training.open') }}</a>
            <UiButton v-if="m.body" size="sm" variant="ghost" @click="expanded = expanded === m.id ? null : m.id">{{ expanded === m.id ? t('common.hide') : t('training.read') }}</UiButton>
            <UiButton v-if="!m.done_at && m.kind !== 'test'" size="sm" variant="navy" icon="ok" :loading="marking === m.id" @click="markDone(m)">{{ t('training.markDone') }}</UiButton>
            <UiChip v-if="!m.done_at && m.kind === 'test'" small icon="tests">{{ t('training.testSoon') }}</UiChip>
          </div>
          <div v-if="expanded === m.id && m.body" class="doc-scroll" style="margin-top: 6px"><DocBody :body="m.body" /></div>
        </div>
      </div>
    </UiCard>
  </template>

  <UiModal v-model:open="adding" :title="t('training.addMaterial')">
    <form id="mat-form" class="stack" @submit.prevent="add">
      <UiSegmented v-model="form.kind" :options="kinds" :label="t('training.kindLabel')" block />
      <UiInput v-model="form.title" :label="t('training.title')" :maxlength="255" />
      <UiInput v-model="form.url" :label="t('training.url')" placeholder="https://" :maxlength="255" />
      <UiTextarea v-model="form.body" :label="t('training.body')" :rows="6" :maxlength="50000" />
      <p v-if="error" class="form-err" role="alert">{{ error }}</p>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton type="submit" form="mat-form" variant="navy" :loading="busy">{{ t('common.add') }}</UiButton>
    </template>
  </UiModal>
</template>
