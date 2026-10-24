<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { UiButton, UiCard, UiChip, UiEmptyState, UiIcon } from '@/components/ui'
import { adminApi, type ImportPreview } from '@/api/admin'
import { useAuthStore } from '@/stores/auth'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import { money } from '@/utils/dates'
import { apiErr } from '@/utils/err'
import type { Locale } from '@/i18n'

/** Excel import of existing students: download the template, upload, check the preview and row errors, then commit the same file. */
const { t, locale } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const refs = useRefsStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)
const file = ref<File | null>(null)
const preview = ref<ImportPreview | null>(null)
const busy = ref<'tpl' | 'check' | 'commit' | null>(null)
const error = ref<string | null>(null)
const dragging = ref(false)
const input = ref<HTMLInputElement | null>(null)
refs.load()

const hasBalances = computed(() => preview.value?.preview.some((r) => r.lessons_left > 0) ?? false)
const balanceBlocked = computed(() => hasBalances.value && !auth.can('payments.create'))

async function template() {
  busy.value = 'tpl'
  try {
    await adminApi.importTemplate()
  } finally {
    busy.value = null
  }
}
async function pick(f: File | null | undefined) {
  if (!f) return
  if (!/\.xlsx$/i.test(f.name)) {
    error.value = t('import.onlyXlsx')
    return
  }
  file.value = f
  preview.value = null
  error.value = null
  busy.value = 'check'
  try {
    preview.value = await adminApi.importStudents(f, false)
  } catch (e) {
    error.value = apiErr(e) ?? t('errors.generic')
  } finally {
    busy.value = null
  }
}
function onDrop(e: DragEvent) {
  dragging.value = false
  pick(e.dataTransfer?.files?.[0])
}
async function commit() {
  if (!file.value) return
  busy.value = 'commit'
  error.value = null
  try {
    const r = await adminApi.importStudents(file.value, true)
    toast.ok(t('import.done', { n: r.created ?? 0 }))
    router.push('/students')
  } catch (e) {
    error.value = apiErr(e) ?? t('errors.generic')
  } finally {
    busy.value = null
  }
}
function clear() {
  file.value = null
  preview.value = null
  error.value = null
  if (input.value) input.value.value = ''
}
</script>

<template>
  <nav class="crumbs" :aria-label="t('common.breadcrumbs')"><RouterLink to="/students">{{ t('students.title') }}</RouterLink> / <span>{{ t('import.title') }}</span></nav>
  <div class="ph">
    <div><h1>{{ t('import.title') }}</h1><p>{{ t('import.subtitle') }}</p></div>
    <span class="sp" />
    <UiButton icon="dl" :loading="busy === 'tpl'" @click="template">{{ t('import.template') }}</UiButton>
  </div>

  <ol class="import-steps">
    <li :class="{ ok: true }"><b>1</b>{{ t('import.step1') }}</li>
    <li :class="{ ok: !!preview }"><b>2</b>{{ t('import.step2') }}</li>
    <li :class="{ ok: false }"><b>3</b>{{ t('import.step3') }}</li>
  </ol>

  <UiCard>
    <label
      class="drop"
      :class="{ over: dragging, has: !!file }"
      @dragover.prevent="dragging = true"
      @dragleave="dragging = false"
      @drop.prevent="onDrop"
    >
      <input ref="input" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" class="sr" @change="pick(($event.target as HTMLInputElement).files?.[0])" />
      <UiIcon name="file" :size="24" />
      <b v-if="file">{{ file.name }}</b>
      <b v-else>{{ t('import.drop') }}</b>
      <span class="muted">{{ busy === 'check' ? t('import.checking') : t('import.dropHint') }}</span>
    </label>
    <p v-if="error" class="form-err" role="alert" style="margin-top: 12px">{{ error }}</p>
  </UiCard>

  <template v-if="preview">
    <div class="toolbar" style="margin-top: 16px">
      <UiChip tone="ok" icon="ok">{{ t('import.valid', { n: preview.valid }) }}</UiChip>
      <UiChip v-if="preview.errors.length" tone="red" icon="alert">{{ t('import.errorsN', { n: preview.errors.length }) }}</UiChip>
      <span class="sp" />
      <UiButton variant="ghost" @click="clear">{{ t('import.another') }}</UiButton>
      <UiButton variant="primary" icon="ok" :loading="busy === 'commit'" :disabled="!!preview.errors.length || !preview.valid || balanceBlocked" @click="commit">{{ t('import.commit', { n: preview.valid }) }}</UiButton>
    </div>
    <div v-if="balanceBlocked" class="alert red"><span>{{ t('import.balanceBlocked') }}</span></div>
    <div v-else-if="preview.errors.length" class="alert"><span>{{ t('import.fixFirst') }}</span></div>

    <UiCard v-if="preview.errors.length" :title="t('import.errorsTitle')" style="margin-bottom: 16px">
      <div v-for="e in preview.errors" :key="`${e.row}-${e.error}`" class="list-row">
        <span class="chip redc num">{{ t('import.row', { n: e.row }) }}</span>
        <div class="grow"><b style="white-space: normal">{{ e.error }}</b></div>
      </div>
    </UiCard>

    <UiCard :title="t('import.previewTitle', { n: Math.min(50, preview.valid), total: preview.valid })" flush>
      <UiEmptyState v-if="!preview.preview.length" icon="users" :title="t('import.noValid')" />
      <div v-else class="scroll-x">
        <table class="tbl" style="min-width: 860px">
          <thead><tr><th>#</th><th>{{ t('staff.name') }}</th><th>{{ t('staff.phone') }}</th><th>{{ t('branch.label') }}</th><th>{{ t('books.level') }}</th><th class="r">{{ t('import.lessons') }}</th><th class="r">{{ t('import.price') }}</th><th>{{ t('import.parent') }}</th></tr></thead>
          <tbody>
            <tr v-for="r in preview.preview" :key="r.row">
              <td class="num muted">{{ r.row }}</td>
              <td><b>{{ r.full_name }}</b><div v-if="r.birth_date" class="muted num" style="font-size: 12px">{{ r.birth_date }}</div></td>
              <td class="num">{{ r.phone ?? '—' }}</td>
              <td>{{ refs.branchName(r.branch_id) }}</td>
              <td>{{ refs.level(r.level_id)?.name ?? '—' }}<div v-if="r.group_id" class="muted" style="font-size: 12px">{{ t('import.groupN', { n: r.group_id }) }}</div></td>
              <td class="r num">{{ r.lessons_left }}</td>
              <td class="r num">{{ money(r.lesson_price, loc) }}</td>
              <td>{{ r.parent_name ?? '—' }}<div v-if="r.parent_phone" class="muted num" style="font-size: 12px">{{ r.parent_phone }}</div></td>
            </tr>
          </tbody>
        </table>
      </div>
    </UiCard>
  </template>
</template>
