<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiField, UiIcon, UiModal, UiSelect, UiSkeleton, UiTextarea } from '@/components/ui'
import { studentsApi, type Student, type TransferPreview } from '@/api/students'
import { academicsApi, type Group } from '@/api/academics'
import { ApiError } from '@/api/http'
import { useToastStore } from '@/stores/toast'
import { money } from '@/utils/dates'
import type { Locale } from '@/i18n'

const props = defineProps<{ student: Student }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ done: [Student] }>()
const { t, locale } = useI18n()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)

const groups = ref<Group[]>([])
const target = ref(0)
const reason = ref('')
const preview = ref<TransferPreview | null>(null)
const error = ref<string | null>(null)
const loadingPreview = ref(false)
const busy = ref(false)

const current = computed(() => new Set(props.student.groups.filter((g) => !g.left_on).map((g) => g.id)))
const options = computed(() => [
  { value: 0, label: t('students.transfer.pick') },
  ...groups.value
    .filter((g) => !current.value.has(g.id) && g.status !== 'finished')
    .map((g) => ({ value: g.id, label: `${g.name} · ${g.members}/${g.capacity}${g.teacher_name ? ` · ${g.teacher_name}` : ''}` })),
])

watch(open, async (v) => {
  if (!v) return
  target.value = 0
  reason.value = ''
  preview.value = null
  error.value = null
  groups.value = await academicsApi.groups({ branch_id: props.student.branch_id }).catch(() => [])
})

watch(target, async (id) => {
  preview.value = null
  error.value = null
  if (!id) return
  loadingPreview.value = true
  try {
    preview.value = await studentsApi.transferPreview(props.student.id, id)
  } catch (e) {
    error.value = e instanceof ApiError ? e.detail : null
  } finally {
    loadingPreview.value = false
  }
})

async function submit() {
  if (!target.value || !preview.value) return
  if (reason.value.trim().length < 3) {
    error.value = t('nv.transferReason')
    return
  }
  error.value = null
  busy.value = true
  try {
    const s = await studentsApi.transfer(props.student.id, target.value, reason.value.trim() || null)
    toast.ok(t('students.transfer.done', { group: preview.value.to_group }))
    emit('done', s)
    open.value = false
  } catch (e) {
    if (e instanceof ApiError) error.value = e.detail
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiModal v-model:open="open" :title="t('students.transfer.title')">
    <form id="tr-form" class="stack" @submit.prevent="submit">
      <UiField :label="t('students.transfer.to')">
        <UiSelect v-model="target" :options="options" :label="t('students.transfer.to')" block />
      </UiField>
      <UiSkeleton v-if="loadingPreview" :lines="4" />
      <div v-else-if="preview" class="tr-prev">
        <div class="tr-flow">
          <div><small>{{ t('students.transfer.from') }}</small><b>{{ preview.from_group ?? '—' }}</b><span>{{ preview.from_level ?? '' }}</span></div>
          <UiIcon name="arrow" />
          <div><small>{{ t('students.transfer.to') }}</small><b>{{ preview.to_group }}</b><span>{{ preview.to_level }}</span></div>
        </div>
        <dl class="kv">
          <dt>{{ t('students.transfer.lessons') }}</dt>
          <dd class="num">{{ preview.lessons_before }} → <b>{{ preview.lessons_after }}</b></dd>
          <template v-if="!preview.same_price">
            <dt>{{ t('students.transfer.price') }}</dt>
            <dd class="num">{{ money(preview.old_price, loc) }} → {{ money(preview.new_price, loc) }}</dd>
            <dt>{{ t('students.transfer.value') }}</dt>
            <dd class="num">{{ money(preview.value, loc) }}</dd>
          </template>
          <dt>{{ t('students.transfer.money') }}</dt>
          <dd class="num">{{ money(preview.money_before, loc) }} → <b>{{ money(preview.money_after, loc) }}</b></dd>
        </dl>
        <div v-if="!preview.same_price" class="alert info"><UiIcon name="alert" /><div class="grow"><span>{{ t('students.transfer.recalc') }}</span></div></div>
        <div v-if="preview.book_hint" class="alert"><UiIcon name="book" /><div class="grow"><span>{{ preview.book_hint }}</span></div></div>
      </div>
      <UiTextarea v-model="reason" :label="t('students.transfer.reason')" :rows="2" :maxlength="255" required />
      <p v-if="error" class="form-err m0" role="alert">{{ error }}</p>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="navy" type="submit" form="tr-form" icon="arrow" :loading="busy" :disabled="!preview">{{ t('students.transfer.confirm') }}</UiButton>
    </template>
  </UiModal>
</template>
