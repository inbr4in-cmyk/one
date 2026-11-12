<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiDrawer, UiField, UiInput, UiPhoneInput, UiSegmented } from '@/components/ui'
import { adminApi, type AssignableRole, type PayScheme, type Staff } from '@/api/admin'
import { useBranchStore } from '@/stores/branch'
import { useToastStore } from '@/stores/toast'
import { apiErr } from '@/utils/err'
import { isCompletePhone } from '@/utils/phone'

/** Create or edit a staff member: position, salary, roles (only ones the editor may grant; the server re-checks), branches. */
const props = defineProps<{ staff: Staff | null; roles: AssignableRole[] }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ saved: [Staff] }>()
const { t, te } = useI18n()
const branch = useBranchStore()
const toast = useToastStore()
const form = reactive({ full_name: '', phone: '', position: '', salary: '', pay_scheme: 'rates' as PayScheme, password: '', role_ids: [] as number[], branch_ids: [] as number[] })
const error = ref<string | null>(null)
const busy = ref(false)

const branches = computed(() => branch.options.filter((o) => o.id !== null) as { id: number; name: string }[])
const roleChoices = computed(() => props.roles)
const schemeOptions = computed(() => (['rates', 'salary', 'both'] as const).map((v) => ({ value: v, label: t(`staff.scheme.${v}`) })))

watch(open, (v) => {
  if (!v) return
  const s = props.staff
  Object.assign(form, {
    full_name: s?.full_name ?? '', phone: '', position: s?.position ?? '', salary: s?.salary != null ? String(s.salary) : '', pay_scheme: s?.pay_scheme ?? 'rates', password: '',
    role_ids: s?.roles.map((r) => r.id) ?? [], branch_ids: s?.branch_ids ?? (branch.filterId !== null ? [branch.filterId] : []),
  })
  error.value = null
})
const toggle = (list: number[], id: number) => (list.includes(id) ? list.splice(list.indexOf(id), 1) : list.push(id))

async function submit() {
  error.value = form.full_name.trim().length < 2 ? t('staff.nameRequired')
    : !props.staff && !isCompletePhone(form.phone) ? t('staff.phoneRequired')
    : props.staff && props.staff.phone === null && form.phone && !isCompletePhone(form.phone) ? t('staff.phoneRequired')
    : !form.branch_ids.length ? t('staff.branchRequired') : null
  if (error.value) return
  busy.value = true
  try {
    const common = { full_name: form.full_name.trim(), position: form.position.trim() || null, branch_ids: form.branch_ids, ...(props.roles.length ? { role_ids: form.role_ids } : {}) }
    const salary = form.salary === '' ? undefined : Math.max(0, Math.round(Number(form.salary)))
    const out = props.staff
      ? await adminApi.updateStaff(props.staff.id, {
        ...common, ...(salary !== undefined ? { salary } : {}), ...(props.staff.pay_scheme !== null ? { pay_scheme: form.pay_scheme } : {}),
        // Imported from the old CRM without a phone: the phone is set here once (then the owner sets a password)
        ...(props.staff.phone === null && form.phone ? { phone: form.phone } : {}),
      })
      : await adminApi.createStaff({ ...common, role_ids: form.role_ids, phone: form.phone, salary: salary ?? 0, pay_scheme: form.pay_scheme, password: form.password || null })
    toast.ok(props.staff ? t('common.saved') : t('staff.created'))
    emit('saved', out)
    open.value = false
  } catch (e) {
    error.value = apiErr(e) ?? t('errors.generic')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiDrawer v-model:open="open" :title="staff ? t('staff.editTitle') : t('staff.newTitle')">
    <form id="staff-form" class="stack" @submit.prevent="submit">
      <UiInput v-model="form.full_name" :label="t('staff.name')" :maxlength="255" autocomplete="off" />
      <UiPhoneInput v-if="!staff" v-model="form.phone" :label="t('staff.phone')" />
      <UiPhoneInput v-else-if="staff.phone === null" v-model="form.phone" :label="t('staff.phone')" />
      <div class="form-2">
        <UiInput v-model="form.position" :label="t('staff.position')" :placeholder="t('staff.positionPh')" :maxlength="255" />
        <UiInput v-if="!staff || staff.salary !== null" v-model="form.salary" type="number" :min="0" :label="t('staff.salary')" inputmode="numeric" />
      </div>
      <UiField v-if="!staff || staff.salary !== null" :label="t('staff.payScheme')">
        <UiSegmented v-model="form.pay_scheme" :options="schemeOptions" :label="t('staff.payScheme')" size="sm" />
      </UiField>
      <UiInput v-if="!staff" v-model="form.password" type="password" :label="t('staff.password')" :hint="t('staff.passwordHint')" autocomplete="new-password" />
      <UiField :label="t('staff.branches')">
        <div class="picker-list short">
          <button v-for="b in branches" :key="b.id" type="button" class="list-row pick" role="checkbox" :aria-checked="form.branch_ids.includes(b.id)" @click="toggle(form.branch_ids, b.id)">
            <span class="cbox" :class="{ on: form.branch_ids.includes(b.id) }" /><span class="grow">{{ b.name }}</span>
          </button>
        </div>
      </UiField>
      <UiField v-if="roles.length" :label="t('staff.roles')">
        <div class="picker-list short">
          <button v-for="r in roleChoices" :key="r.id" type="button" class="list-row pick" role="checkbox" :aria-checked="form.role_ids.includes(r.id)" @click="toggle(form.role_ids, r.id)">
            <span class="cbox" :class="{ on: form.role_ids.includes(r.id) }" /><span class="grow"><b>{{ te(`roles.${r.code}`) ? t(`roles.${r.code}`) : r.name }}</b><span v-if="r.description">{{ r.description }}</span></span>
          </button>
        </div>
      </UiField>
      <p v-else class="form-note">{{ t('staff.noRolesAccess') }}</p>
      <p v-if="error" class="form-err" role="alert">{{ error }}</p>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton type="submit" form="staff-form" variant="navy" :loading="busy">{{ staff ? t('common.save') : t('staff.create') }}</UiButton>
    </template>
  </UiDrawer>
</template>
