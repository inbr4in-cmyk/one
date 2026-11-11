<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiCheck, UiInput, UiModal, UiPhoneInput } from '@/components/ui'
import { studentsApi, type Guardian, type Student } from '@/api/students'
import { ApiError } from '@/api/http'
import { useToastStore } from '@/stores/toast'

/** Add a parent, or edit one (`guardian` given): name, phone, relation, WhatsApp notifications. */
const props = defineProps<{ student: Student; guardian?: Guardian | null }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ done: [Student] }>()
const { t, locale } = useI18n()
const toast = useToastStore()
const form = reactive({ full_name: '', phone: '', relation: '', notify: true })
const errors = reactive<{ name: string | null; phone: string | null }>({ name: null, phone: null })
const busy = ref(false)

watch(open, (v) => {
  if (!v) return
  const g = props.guardian
  Object.assign(form, g
    ? { full_name: g.full_name, phone: g.phone && !g.phone.includes('*') ? g.phone : '', relation: g.relation ?? '', notify: g.notify }
    : { full_name: '', phone: '', relation: '', notify: true })
  errors.name = errors.phone = null
})

async function submit() {
  errors.name = form.full_name.trim().length < 2 ? t('students.form.nameRequired') : null
  errors.phone = form.phone || props.guardian ? null : t('login.phoneInvalid')
  if (errors.name || errors.phone) return
  busy.value = true
  try {
    const g = props.guardian
    const s = g
      ? await studentsApi.editGuardian(props.student.id, g.id, {
        full_name: form.full_name.trim(), relation: form.relation.trim() || null, notify: form.notify,
        ...(form.phone && form.phone !== g.phone ? { phone: form.phone } : {}),
      })
      : await studentsApi.addGuardian(props.student.id, {
      full_name: form.full_name.trim(), phone: form.phone, relation: form.relation.trim() || null, notify: form.notify,
      locale: locale.value as 'ru' | 'kk',
    })
    toast.ok(g ? t('common.saved') : t('students.guardianAdded'))
    emit('done', s)
    open.value = false
  } catch (e) {
    if (e instanceof ApiError) errors.phone = e.detail || t('errors.generic')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiModal v-model:open="open" :title="guardian ? t('students.editGuardian') : t('students.addGuardian')">
    <form id="gd-form" class="stack" novalidate @submit.prevent="submit">
      <UiInput v-model="form.full_name" :label="t('students.form.guardianName')" :error="errors.name" autofocus />
      <div class="form-2">
        <UiPhoneInput v-model="form.phone" :label="t('students.form.phone')" :error="errors.phone" :hint="guardian && !form.phone ? t('students.guardianPhoneKeep') : undefined" />
        <UiInput v-model="form.relation" :label="t('students.form.relation')" :placeholder="t('students.form.relationPh')" />
      </div>
      <UiCheck v-model="form.notify" :label="t('students.form.notify')" />
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="navy" type="submit" form="gd-form" :loading="busy">{{ guardian ? t('common.save') : t('common.add') }}</UiButton>
    </template>
  </UiModal>
</template>
