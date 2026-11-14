<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiField, UiInput, UiModal, UiSegmented, UiTextarea } from '@/components/ui'
import { studentsApi, type Student } from '@/api/students'
import { ApiError } from '@/api/http'
import { useToastStore } from '@/stores/toast'

/** The methodist's decision after talking to the student: really left (reason, when they may return) or stays. */
const props = defineProps<{ student: Student }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ done: [Student] }>()
const { t } = useI18n()
const toast = useToastStore()
const form = reactive({ left: 'left' as 'left' | 'stay', reason: '', return_note: '' })
const error = ref<string | null>(null)
const busy = ref(false)
const options = computed(() => [{ value: 'left' as const, label: t('nv.leave.left') }, { value: 'stay' as const, label: t('nv.leave.stay') }])

watch(open, (v) => {
  if (!v) return
  Object.assign(form, { left: 'left', reason: props.student.leave_reason ?? '', return_note: props.student.return_note ?? '' })
  error.value = null
})

async function submit() {
  if (form.reason.trim().length < 3) {
    error.value = form.left === 'left' ? t('nv.leave.reasonRequired') : t('nv.leave.stayRequired')
    return
  }
  error.value = null
  busy.value = true
  try {
    const s = await studentsApi.leaveDecision(props.student.id, {
      left: form.left === 'left', reason: form.reason.trim(), return_note: form.left === 'left' ? form.return_note.trim() || null : null,
    })
    toast.ok(t('common.saved'))
    emit('done', s)
    open.value = false
  } catch (e) {
    error.value = e instanceof ApiError ? e.detail : t('errors.generic')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiModal v-model:open="open" :title="t('nv.leave.title')">
    <form id="leave-form" class="stack" novalidate @submit.prevent="submit">
      <p class="muted m0">{{ student.full_name }}</p>
      <UiField :label="t('nv.leave.decision')">
        <UiSegmented v-model="form.left" :options="options" :label="t('nv.leave.decision')" size="sm" />
      </UiField>
      <UiTextarea v-model="form.reason" :label="form.left === 'left' ? t('nv.leave.reason') : t('nv.leave.stayNote')" :rows="3" :maxlength="500" autofocus />
      <UiInput v-if="form.left === 'left'" v-model="form.return_note" :label="t('nv.leave.returnNote')" :maxlength="500" />
      <p v-if="error" class="form-err m0" role="alert">{{ error }}</p>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="navy" type="submit" form="leave-form" :loading="busy">{{ t('common.save') }}</UiButton>
    </template>
  </UiModal>
</template>
