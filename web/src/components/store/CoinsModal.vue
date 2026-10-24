<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiAvatar, UiButton, UiInput, UiModal, UiSegmented } from '@/components/ui'
import StudentPicker from '@/components/students/StudentPicker.vue'
import { coinsApi } from '@/api/store'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import { apiErr } from '@/utils/err'

/** Award or write off coins, always with a reason. The monthly award limit is enforced (and reported) by the server. */
const props = defineProps<{ student?: { id: number; full_name: string } | null; mode?: 'award' | 'writeoff' }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ done: [balance: number] }>()
const { t } = useI18n()
const auth = useAuthStore()
const toast = useToastStore()

const kind = ref<'award' | 'writeoff'>('award')
const who = ref<{ id: number; full_name: string } | null>(null)
const amount = ref('')
const reason = ref('')
const error = ref<string | null>(null)
const busy = ref(false)
const kinds = computed(() => [
  ...(auth.can('coins.award') ? [{ value: 'award' as const, label: t('coins.award') }] : []),
  ...(auth.can('coins.writeoff') ? [{ value: 'writeoff' as const, label: t('coins.writeoff') }] : []),
])

watch(open, (v) => {
  if (!v) return
  kind.value = props.mode ?? kinds.value[0]?.value ?? 'award'
  who.value = props.student ?? null
  amount.value = ''
  reason.value = ''
  error.value = null
})

async function submit() {
  const n = Math.round(Number(amount.value))
  error.value = !who.value ? t('coins.pickStudent') : !(n > 0) ? t('coins.amountInvalid') : reason.value.trim().length < 3 ? t('common.reasonRequired') : null
  if (error.value || !who.value) return
  busy.value = true
  try {
    const body = { student_id: who.value.id, amount: n, reason: reason.value.trim() }
    if (kind.value === 'award') {
      const r = await coinsApi.award(body)
      toast.ok(t('coins.awarded', { n, left: r.limit_left }))
      emit('done', r.balance)
    } else {
      const r = await coinsApi.writeoff(body)
      toast.ok(t('coins.writtenOff', { n }))
      emit('done', r.balance)
    }
    open.value = false
  } catch (e) {
    error.value = apiErr(e) ?? t('errors.generic')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiModal v-model:open="open" :title="kind === 'award' ? t('coins.awardTitle') : t('coins.writeoffTitle')">
    <form id="coins-form" class="stack" @submit.prevent="submit">
      <UiSegmented v-if="kinds.length > 1" v-model="kind" :options="kinds" :label="t('coins.title')" block />
      <div v-if="who" class="who2 who-box">
        <UiAvatar :name="who.full_name" size="sm" />
        <b class="grow">{{ who.full_name }}</b>
        <UiButton v-if="!props.student" size="sm" variant="ghost" @click="who = null">{{ t('common.edit') }}</UiButton>
      </div>
      <StudentPicker v-else @pick="(s) => (who = s)" />
      <UiInput v-model="amount" type="number" :min="1" :label="t('coins.amount')" inputmode="numeric" />
      <UiInput v-model="reason" :label="t('common.reason')" :placeholder="kind === 'award' ? t('coins.reasonPh') : t('coins.writeoffPh')" :maxlength="255" />
      <p v-if="kind === 'award'" class="form-note">{{ t('coins.limitNote') }}</p>
      <p v-if="error" class="form-err" role="alert">{{ error }}</p>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton type="submit" form="coins-form" :variant="kind === 'award' ? 'navy' : 'primary'" icon="coin" :loading="busy">{{ kind === 'award' ? t('coins.award') : t('coins.writeoff') }}</UiButton>
    </template>
  </UiModal>
</template>
