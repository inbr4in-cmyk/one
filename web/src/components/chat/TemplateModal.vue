<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiField, UiIcon, UiInput, UiModal, UiSelect } from '@/components/ui'
import { inboxApi, type Conversation, type InboxMessage } from '@/api/inbox'

/**
 * WhatsApp templates for replies after the 24h window. The backend has no endpoint that lists
 * templates, so the codes and their variables are known here (see the seeded TEMPLATES).
 */
const CATALOG: Record<string, string[]> = {
  pay_reminder: ['name', 'left'],
  lesson_move: ['group', 'date', 'time', 'reason'],
  lesson_cancel: ['group', 'date', 'time', 'reason'],
  absence: ['name', 'time', 'group'],
}

const props = defineProps<{ conversation: Conversation | null }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ sent: [InboxMessage] }>()
const { t } = useI18n()
const code = ref('pay_reminder')
const vars = reactive<Record<string, string>>({})
const busy = ref(false)

const options = computed(() => Object.keys(CATALOG).map((c) => ({ value: c, label: t(`inbox.tpl.${c}`) })))
const fields = computed(() => CATALOG[code.value] ?? [])
const preview = computed(() => t(`inbox.tplText.${code.value}`, Object.fromEntries(fields.value.map((k) => [k, vars[k]?.trim() || `‹${t(`inbox.var.${k}`)}›`]))))
const ready = computed(() => fields.value.every((k) => vars[k]?.trim()))

watch(open, (v) => {
  if (!v) return
  Object.keys(vars).forEach((k) => delete vars[k])
  vars.name = props.conversation?.lead?.full_name ?? props.conversation?.contact.name ?? ''
})

async function send() {
  if (!props.conversation || !ready.value) return
  busy.value = true
  try {
    const body = Object.fromEntries(fields.value.map((k) => [k, vars[k]!.trim()]))
    emit('sent', await inboxApi.template(props.conversation.id, code.value, body))
    open.value = false
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiModal v-model:open="open" :title="t('inbox.tplTitle')">
    <form id="tpl-form" class="stack" @submit.prevent="send">
      <div class="alert info"><UiIcon name="clock" /><div class="grow"><span>{{ t('inbox.windowClosed') }}</span></div></div>
      <UiField :label="t('inbox.tplPick')"><UiSelect v-model="code" :options="options" :label="t('inbox.tplPick')" block /></UiField>
      <div class="form-2">
        <UiInput v-for="k in fields" :key="k" :model-value="vars[k] ?? ''" @update:model-value="(v: string) => (vars[k] = v)" :label="t(`inbox.var.${k}`)" />
      </div>
      <div class="b out tpl-prev">{{ preview }}</div>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="primary" type="submit" form="tpl-form" icon="send" :loading="busy" :disabled="!ready">{{ t('inbox.sendTpl') }}</UiButton>
    </template>
  </UiModal>
</template>
