<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiField, UiIcon, UiInput, UiModal, UiSegmented, UiSelect, UiSkeleton } from '@/components/ui'
import { inboxApi, type Conversation, type InboxMessage, type MessageTemplate } from '@/api/inbox'

/** WhatsApp templates for replies after the 24 h window; the list and bodies come from GET /message-templates. */
const props = defineProps<{ conversation: Conversation | null }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ sent: [InboxMessage] }>()
const { t, te, locale } = useI18n()
const templates = ref<MessageTemplate[] | null>(null)
const code = ref('')
const lang = ref<'ru' | 'kk'>('ru')
const vars = reactive<Record<string, string>>({})
const busy = ref(false)

const label = (prefix: string, k: string) => (te(`${prefix}.${k}`) ? t(`${prefix}.${k}`) : k)
const codes = computed(() => [...new Set((templates.value ?? []).map((x) => x.code))])
const options = computed(() => codes.value.map((c) => ({ value: c, label: label('inbox.tpl', c) })))
const langs = computed(() => (['ru', 'kk'] as const).filter((l) => templates.value?.some((x) => x.code === code.value && x.locale === l))
  .map((l) => ({ value: l, label: t(`lang.${l}`) })))
const current = computed(() => templates.value?.find((x) => x.code === code.value && x.locale === lang.value)
  ?? templates.value?.find((x) => x.code === code.value))
const fields = computed(() => current.value?.variables ?? [])
const preview = computed(() => (current.value?.body ?? '').replace(/\{(\w+)\}/g, (_, k: string) => vars[k]?.trim() || `‹${label('inbox.var', k)}›`))
const ready = computed(() => !!current.value && fields.value.every((k) => vars[k]?.trim()))

watch(open, async (v) => {
  if (!v) return
  Object.keys(vars).forEach((k) => delete vars[k])
  vars.name = props.conversation?.lead?.full_name ?? props.conversation?.contact.name ?? ''
  lang.value = locale.value === 'kk' ? 'kk' : 'ru'
  templates.value ??= await inboxApi.templates().catch(() => [])
  if (!codes.value.includes(code.value)) code.value = props.conversation?.lead ? (codes.value.find((c) => c === 'followup') ?? codes.value[0] ?? '') : (codes.value[0] ?? '')
})
watch(code, () => {
  if (!langs.value.some((l) => l.value === lang.value)) lang.value = langs.value[0]?.value ?? 'ru'
})

async function send() {
  const c = props.conversation
  const tpl = current.value
  if (!c || !tpl || !ready.value) return
  busy.value = true
  try {
    const body = Object.fromEntries(fields.value.map((k) => [k, vars[k]!.trim()]))
    emit('sent', await inboxApi.template(c.id, tpl.code, body, tpl.locale))
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
      <UiSkeleton v-if="!templates" :lines="3" />
      <p v-else-if="!templates.length" class="muted">{{ t('inbox.tplNone') }}</p>
      <template v-else>
        <div class="form-2">
          <UiField :label="t('inbox.tplPick')"><UiSelect v-model="code" :options="options" :label="t('inbox.tplPick')" block /></UiField>
          <UiField v-if="langs.length > 1" :label="t('inbox.tplLang')"><UiSegmented v-model="lang" :options="langs" :label="t('inbox.tplLang')" /></UiField>
        </div>
        <div class="form-2">
          <UiInput v-for="k in fields" :key="k" :model-value="vars[k] ?? ''" @update:model-value="(v: string) => (vars[k] = v)" :label="label('inbox.var', k)" />
        </div>
        <div class="b out tpl-prev">{{ preview }}</div>
      </template>
    </form>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="primary" type="submit" form="tpl-form" icon="send" :loading="busy" :disabled="!ready">{{ t('inbox.sendTpl') }}</UiButton>
    </template>
  </UiModal>
</template>
