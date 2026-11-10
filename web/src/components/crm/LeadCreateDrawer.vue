<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiDrawer, UiField, UiInput, UiPhoneInput, UiSelect, UiTextarea } from '@/components/ui'
import { crmApi, type Lead, type LeadSource } from '@/api/crm'
import { useSourcesStore } from '@/stores/sources'
import { ApiError } from '@/api/http'
import { useBranchStore } from '@/stores/branch'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'

const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ created: [Lead] }>()
const { t } = useI18n()
const branch = useBranchStore()
const refs = useRefsStore()
const toast = useToastStore()
const form = reactive({ full_name: '', phone: '', branch_id: 0, source: 'sales' as LeadSource, age: '', parent_name: '', parent_phone: '', level_id: 0, notes: '' })
const errors = reactive<{ name: string | null; phone: string | null }>({ name: null, phone: null })
const busy = ref(false)

const branchOptions = computed(() => branch.options.filter((o) => o.id !== null).map((o) => ({ value: o.id as number, label: o.name })))
const sources = useSourcesStore()
void sources.load()
const sourceOptions = computed(() => sources.options(form.source).filter((o) => o.value !== 'import' && o.value !== 'return'))
const levelOptions = computed(() => [{ value: 0, label: t('students.noLevel') }, ...refs.levels.map((l) => ({ value: l.id, label: l.name }))])
const isChild = computed(() => Number(form.age) > 0 && Number(form.age) < 18)

watch(open, (v) => {
  if (!v) return
  Object.assign(form, { full_name: '', phone: '', branch_id: branch.filterId ?? branchOptions.value[0]?.value ?? 0, source: 'sales', age: '', parent_name: '', parent_phone: '', level_id: 0, notes: '' })
  errors.name = errors.phone = null
})

async function submit() {
  errors.name = form.full_name.trim().length < 2 ? t('students.form.nameRequired') : null
  errors.phone = null
  if (errors.name) return
  busy.value = true
  try {
    const lead = await crmApi.create({
      full_name: form.full_name.trim(), phone: form.phone || null, branch_id: form.branch_id, source: form.source,
      age: Number(form.age) || null, parent_name: form.parent_name.trim() || null, parent_phone: form.parent_phone || null,
      level_id: form.level_id || null, notes: form.notes.trim() || null,
    })
    toast.ok(t('crm.created'))
    emit('created', lead)
    open.value = false
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) errors.phone = e.detail
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiDrawer v-model:open="open" :title="t('crm.newLead')">
    <form id="lead-form" class="stack" novalidate @submit.prevent="submit">
      <UiInput v-model="form.full_name" :label="t('students.form.name')" :error="errors.name" autofocus />
      <div class="form-2">
        <UiPhoneInput v-model="form.phone" :label="t('students.form.phone')" :error="errors.phone" />
        <UiInput v-model="form.age" type="number" :min="3" :max="99" :label="t('crm.age')" />
      </div>
      <div class="form-2">
        <UiField :label="t('crm.sourceLabel')"><UiSelect v-model="form.source" :options="sourceOptions" :label="t('crm.sourceLabel')" block /></UiField>
        <UiField :label="t('branch.label')"><UiSelect v-model="form.branch_id" :options="branchOptions" :label="t('branch.label')" block /></UiField>
      </div>
      <UiField :label="t('crm.interest')"><UiSelect v-model="form.level_id" :options="levelOptions" :label="t('crm.interest')" block /></UiField>
      <Transition name="fade">
        <div v-if="isChild" class="form-2">
          <UiInput v-model="form.parent_name" :label="t('crm.parentName')" />
          <UiPhoneInput v-model="form.parent_phone" :label="t('crm.parentPhone')" />
        </div>
      </Transition>
      <UiTextarea v-model="form.notes" :label="t('students.form.notes')" :rows="2" />
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="primary" type="submit" form="lead-form" icon="plus" :loading="busy">{{ t('crm.createLead') }}</UiButton>
    </template>
  </UiDrawer>
</template>
