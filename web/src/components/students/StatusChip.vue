<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import UiChip from '@/components/ui/UiChip.vue'
import type { StudentStatus } from '@/api/students'

defineProps<{ status: StudentStatus; small?: boolean }>()
const { t } = useI18n()
const TONE: Record<StudentStatus, 'ok' | 'warn' | 'red' | 'info' | undefined> = {
  active: 'ok', trial: 'info', lead: 'info', frozen: 'warn', finished: undefined, left: 'red',
}
</script>

<template>
  <UiChip :tone="TONE[status]" :small="small">{{ t(`students.status.${status}`) }}</UiChip>
</template>
