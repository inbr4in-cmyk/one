<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiField, UiInput, UiModal, UiPhoneInput, UiSelect, UiTextarea } from '@/components/ui'
import { studentsApi, type Student } from '@/api/students'
import { LEAD_SOURCES } from '@/api/crm'
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
const form = reactive({ full_name: '', birth_date: '', phone: '', level_id: 0, source: '', notes: '', contract_no: '', contract_date: '' })
const errors = reactive<{ full_name: string | null; phone: string | null; contract: string | null }>({ full_name: null, phone: null, contract: null })
const busy = ref(false)

const levelOptions = computed(() => [{ value: 0, label: t('students.noLevel') }, ...refs.levels.map((l) => ({ value: l.id, label: l.name }))])
const sourceOptions = computed(() => {
  const list: string[] = [...LEAD_SOURCES]
  if (form.source && !list.includes(form.source)) list.push(form.source)
  return [{ value: '', label: '—' }, ...list.map((s) => ({ value: s, label: (LEAD_SOURCES as readonly string[]).includes(s) ? t(`crm.source.${s}`) : s }))]
})
const age = computed(() => ageOf(form.birth_date || null))

watch(open, (v) => {
  if (!v) return
  const s = props.student
  Object.assign(form, {
    full_name: s.full_name, birth_date: s.birth_date ?? '', phone: s.phone ?? '', level_id: s.level_id ?? 0,
    source: s.source ?? '', notes: s.notes ?? '', contract_no: s.contract_no ?? '', contract_date: s.contract_date ?? '',
  })
  errors.full_name = errors.phone = errors.contract = null
})

async function submit() {
  errors.full_name = form.full_name.trim().length < 2 ? t('students.form.nameRequired') : null
  errors.phone = errors.contract = null
  if (errors.full_name) return
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
    })
    toast.ok(t('students.edit.saved'))
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
        <UiPhoneInput v-model="form.phone" :label="t('students.form.phone')" :error="errors.phone" :hint="t('students.edit.phoneHint')" />
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
      <UiTextarea v-model="form.notes" :label="t('students.form.notes')" :rows="3" :maxlength="4000" />
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="navy" type="submit" form="stu-edit" :loading="busy">{{ t('common.save') }}</UiButton>
    </template>
  </UiModal>
</template>
