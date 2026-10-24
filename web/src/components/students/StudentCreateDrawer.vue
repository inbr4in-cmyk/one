<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiCheck, UiDrawer, UiField, UiInput, UiPhoneInput, UiSelect, UiTextarea, UiIcon } from '@/components/ui'
import { studentsApi, type GuardianIn, type Student } from '@/api/students'
import { LEAD_SOURCES } from '@/api/crm'
import { useBranchStore } from '@/stores/branch'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import { ApiError } from '@/api/http'
import { ageOf } from '@/utils/dates'

const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ created: [Student] }>()
const { t, locale } = useI18n()
const branch = useBranchStore()
const refs = useRefsStore()
const toast = useToastStore()

const blank = () => ({
  full_name: '',
  birth_date: '',
  phone: '',
  branch_id: branch.filterId ?? branch.options.find((o) => o.id !== null)?.id ?? 0,
  level_id: 0,
  source: '',
  notes: '',
  create_account: true,
})
const form = reactive(blank())
const guardians = ref<(GuardianIn & { key: number; relation: string; notify: boolean })[]>([])
const errors = reactive<Record<string, string | null>>({})
const busy = ref(false)
let seq = 0

const branchOptions = computed(() => branch.options.filter((o) => o.id !== null).map((o) => ({ value: o.id as number, label: o.name })))
const levelOptions = computed(() => [{ value: 0, label: t('students.noLevel') }, ...refs.levels.map((l) => ({ value: l.id, label: l.name }))])
const sourceOptions = computed(() => [{ value: '', label: '—' }, ...LEAD_SOURCES.map((s) => ({ value: s, label: t(`crm.source.${s}`) }))])
const age = computed(() => ageOf(form.birth_date || null))
/** Children under 18 need a guardian to receive notifications. */
const needsGuardian = computed(() => age.value !== null && age.value < 18)

function addGuardian() {
  guardians.value.push({ key: ++seq, full_name: '', phone: '', relation: '', notify: true, locale: locale.value as 'ru' | 'kk' })
}

watch(open, (v) => {
  if (!v) return
  Object.assign(form, blank())
  guardians.value = []
  Object.keys(errors).forEach((k) => (errors[k] = null))
})
watch(needsGuardian, (v) => v && !guardians.value.length && addGuardian())

function validate(): boolean {
  Object.keys(errors).forEach((k) => (errors[k] = null))
  if (form.full_name.trim().length < 2) errors.full_name = t('students.form.nameRequired')
  if (!form.branch_id) errors.branch = t('students.form.branchRequired')
  guardians.value.forEach((g, i) => {
    if (g.full_name.trim().length < 2) errors[`g${i}name`] = t('students.form.nameRequired')
    if (!g.phone) errors[`g${i}phone`] = t('login.phoneInvalid')
  })
  if (needsGuardian.value && !guardians.value.length) errors.guardians = t('students.form.guardianRequired')
  return !Object.values(errors).some(Boolean)
}

async function submit() {
  if (!validate()) return
  busy.value = true
  try {
    const s = await studentsApi.create({
      full_name: form.full_name.trim(),
      birth_date: form.birth_date || null,
      phone: form.phone || null,
      branch_id: form.branch_id,
      level_id: form.level_id || null,
      source: form.source || null,
      notes: form.notes.trim() || null,
      create_account: form.create_account,
      guardians: guardians.value.map(({ key: _k, ...g }) => ({ ...g, relation: g.relation || null })),
    })
    toast.ok(t('students.created'))
    emit('created', s)
    open.value = false
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) errors.phone = e.detail
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiDrawer v-model:open="open" :title="t('students.new')">
    <form id="stu-create" class="stack" novalidate @submit.prevent="submit">
      <UiInput v-model="form.full_name" :label="t('students.form.name')" :error="errors.full_name" autocomplete="off" autofocus />
      <div class="form-2">
        <UiInput v-model="form.birth_date" type="date" :label="t('students.form.birth')" :hint="age !== null ? t('students.age', { n: age }) : undefined" />
        <UiPhoneInput v-model="form.phone" :label="t('students.form.phone')" :error="errors.phone" />
      </div>
      <div class="form-2">
        <UiField :label="t('branch.label')" :error="errors.branch">
          <UiSelect v-model="form.branch_id" :options="branchOptions" :label="t('branch.label')" block />
        </UiField>
        <UiField :label="t('students.form.level')">
          <UiSelect v-model="form.level_id" :options="levelOptions" :label="t('students.form.level')" block />
        </UiField>
      </div>
      <UiField :label="t('students.form.source')">
        <UiSelect v-model="form.source" :options="sourceOptions" :label="t('students.form.source')" block />
      </UiField>

      <div class="sub-h">
        <b>{{ t('students.guardians') }}</b>
        <span class="sp" />
        <UiButton size="sm" variant="ghost" icon="plus" @click="addGuardian">{{ t('students.form.addGuardian') }}</UiButton>
      </div>
      <p v-if="errors.guardians" class="form-err" role="alert">{{ errors.guardians }}</p>
      <TransitionGroup name="fade" tag="div" class="stack">
        <fieldset v-for="(g, i) in guardians" :key="g.key" class="g-box">
          <legend class="sr">{{ t('students.guardian') }} {{ i + 1 }}</legend>
          <button type="button" class="dlg-x g-x" :aria-label="t('common.remove')" @click="guardians.splice(i, 1)"><UiIcon name="x" :size="16" /></button>
          <UiInput v-model="g.full_name" :label="t('students.form.guardianName')" :error="errors[`g${i}name`]" autocomplete="off" />
          <div class="form-2">
            <UiPhoneInput v-model="g.phone" :label="t('students.form.phone')" :error="errors[`g${i}phone`]" />
            <UiInput v-model="g.relation" :label="t('students.form.relation')" :placeholder="t('students.form.relationPh')" />
          </div>
          <UiCheck v-model="g.notify" :label="t('students.form.notify')" />
        </fieldset>
      </TransitionGroup>

      <UiCheck v-model="form.create_account" :label="t('students.form.account')" :hint="t('students.form.accountHint')" />
      <UiTextarea v-model="form.notes" :label="t('students.form.notes')" :rows="2" />
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="primary" type="submit" form="stu-create" :loading="busy" icon="plus">{{ t('students.create') }}</UiButton>
    </template>
  </UiDrawer>
</template>
