<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiField, UiInput, UiModal, UiPhoneInput, UiSelect, UiTextarea } from '@/components/ui'
import { studentsApi, type Student } from '@/api/students'
import { useSourcesStore } from '@/stores/sources'
import { ApiError } from '@/api/http'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import { ageOf } from '@/utils/dates'

/** Edit the student's card. Shown only with students.edit (managers, admins); teachers don't have it. */
const props = defineProps<{ student: Student }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ done: [Student] }>()
const { t } = useI18n()
const refs = useRefsStore()
const toast = useToastStore()
const form = reactive({ full_name: '', birth_date: '', phone: '', level_id: 0, source: '', notes: '', contract_no: '', contract_date: '', status: '', leave_reason: '', return_note: '' })
const errors = reactive<{ full_name: string | null; phone: string | null; contract: string | null; leave: string | null }>({ full_name: null, phone: null, contract: null, leave: null })
const busy = ref(false)

const levelOptions = computed(() => [{ value: 0, label: t('students.noLevel') }, ...refs.levels.map((l) => ({ value: l.id, label: l.name }))])
const sources = useSourcesStore()
void sources.load()
const sourceOptions = computed(() => {
  const list = sources.options(form.source)
  // An old free-text value (e.g. from the old CRM) stays selectable
  if (form.source && !list.some((o) => o.value === form.source)) list.push({ value: form.source, label: form.source })
  return [{ value: '', label: '—' }, ...list]
})
const canStatus = computed(() => ['active', 'finished', 'left'].includes(props.student.status))
const statusOptions = computed(() => (['active', 'finished', 'left'] as const).map((v) => ({ value: v, label: t(`students.status.${v}`) })))
const age = computed(() => ageOf(form.birth_date || null))
/** «Ушёл» chosen now: the methodist decides (with a reason); other staff only send the request. */
const leaving = computed(() => canStatus.value && form.status === 'left' && props.student.status !== 'left')

watch(open, (v) => {
  if (!v) return
  const s = props.student
  Object.assign(form, {
    full_name: s.full_name, birth_date: s.birth_date ?? '', phone: s.phone ?? '', level_id: s.level_id ?? 0,
    source: s.source ?? '', notes: s.notes ?? '', contract_no: s.contract_no ?? '', contract_date: s.contract_date ?? '', status: s.status, leave_reason: '', return_note: '',
  })
  errors.full_name = errors.phone = errors.contract = errors.leave = null
})

async function submit() {
  errors.full_name = form.full_name.trim().length < 2 ? t('students.form.nameRequired') : null
  errors.phone = errors.contract = null
  errors.leave = leaving.value && props.student.can_decide_leave && form.leave_reason.trim().length < 3 ? t('nv.leave.reasonRequired') : null
  if (errors.full_name || errors.leave) return
  busy.value = true
  try {
    const s = await studentsApi.update(props.student.id, {
      full_name: form.full_name.trim(),
      birth_date: form.birth_date || null,
      phone: form.phone || null,
      level_id: form.level_id || null,
      source: form.source || null,
      notes: form.notes.trim() || null,
      contract_no: form.contract_no.trim() || null,
      contract_date: form.contract_date || null,
      ...(canStatus.value && form.status !== props.student.status ? { status: form.status as 'active' | 'finished' | 'left' } : {}),
      ...(leaving.value ? { leave_reason: form.leave_reason.trim() || null, return_note: form.return_note.trim() || null } : {}),
    })
    toast.ok(leaving.value && !props.student.can_decide_leave ? t('nv.leave.sent') : t('students.edit.saved'))
    emit('done', s)
    open.value = false
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) {
      if (/[Дд]оговор|[Шш]арт/.test(e.detail ?? '')) errors.contract = e.detail
      else errors.phone = e.detail
    }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiModal v-model:open="open" :title="t('students.edit.title')">
    <form id="stu-edit" class="stack" novalidate @submit.prevent="submit">
      <UiInput v-model="form.full_name" :label="t('students.form.name')" :error="errors.full_name" autocomplete="off" autofocus />
      <div class="form-2">
        <UiInput v-model="form.birth_date" type="date" :label="t('students.form.birth')" :hint="age !== null ? t('students.age', { n: age }) : undefined" />
        <UiPhoneInput v-model="form.phone" :label="t('students.form.phone')" :error="errors.phone" />
      </div>
      <div class="form-2">
        <UiField :label="t('students.form.level')">
          <UiSelect v-model="form.level_id" :options="levelOptions" :label="t('students.form.level')" block />
        </UiField>
        <UiField :label="t('students.form.source')">
          <UiSelect v-model="form.source" :options="sourceOptions" :label="t('students.form.source')" block />
        </UiField>
      </div>
      <div class="form-2">
        <UiInput v-model="form.contract_no" :label="t('contract.no')" :error="errors.contract" :maxlength="64" autocomplete="off" />
        <UiInput v-model="form.contract_date" type="date" :label="t('contract.date')" />
      </div>
      <UiField v-if="canStatus" :label="t('students.col.status')">
        <UiSelect v-model="form.status" :options="statusOptions" :label="t('students.col.status')" block />
      </UiField>
      <template v-if="leaving">
        <div v-if="!student.can_decide_leave" class="alert info"><span>{{ t('nv.leave.viaMethodist') }}</span></div>
        <UiTextarea v-model="form.leave_reason" :label="student.can_decide_leave ? t('nv.leave.reason') : t('nv.leave.comment')" :rows="2" :maxlength="500" :error="errors.leave" />
        <UiInput v-if="student.can_decide_leave" v-model="form.return_note" :label="t('nv.leave.returnNote')" :maxlength="500" />
      </template>
      <UiTextarea v-model="form.notes" :label="t('students.form.notes')" :rows="3" :maxlength="4000" />
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="navy" type="submit" form="stu-edit" :loading="busy">{{ t('common.save') }}</UiButton>
    </template>
  </UiModal>
</template>
