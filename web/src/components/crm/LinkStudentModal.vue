<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiAvatar, UiButton, UiModal } from '@/components/ui'
import StudentPicker from '@/components/students/StudentPicker.vue'

/** «Существующий ученик»: pick the student this lead or chat really is, then confirm. */
const props = defineProps<{ busy?: boolean; preset?: { id: number; full_name: string } | null }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ confirm: [number] }>()
const { t } = useI18n()
const who = ref<{ id: number; full_name: string } | null>(null)

watch(open, (v) => v && (who.value = props.preset ?? null))
</script>

<template>
  <UiModal v-model:open="open" :title="t('nv.link.title')">
    <div class="stack">
      <template v-if="who">
        <div class="who2 who-box">
          <UiAvatar :name="who.full_name" size="sm" />
          <b class="grow">{{ who.full_name }}</b>
          <UiButton size="sm" variant="ghost" @click="who = null">{{ t('common.edit') }}</UiButton>
        </div>
        <p class="muted m0">{{ t('nv.link.confirm') }}</p>
      </template>
      <StudentPicker v-else @pick="(s) => (who = { id: s.id, full_name: s.full_name })" />
    </div>
    <template #footer="{ close }">
      <UiButton @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="navy" icon="users" :loading="busy" :disabled="!who" @click="who && emit('confirm', who.id)">{{ t('nv.link.do') }}</UiButton>
    </template>
  </UiModal>
</template>
