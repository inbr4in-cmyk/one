<script setup lang="ts">
// «Задачи | Жалобы»: complaints are opened from inside the tasks page (owner, 27.11.2026); only who may see them gets the switch.
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

defineProps<{ at: 'tasks' | 'complaints' }>()
const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()
</script>

<template>
  <div v-if="auth.can('complaints.view') && auth.can('tasks.view')" class="seg" style="margin-bottom: 12px" data-testid="tasks-switch">
    <button type="button" :aria-pressed="at === 'tasks'" @click="at !== 'tasks' && router.push('/tasks')">{{ t('nav.tasks') }}</button>
    <button type="button" :aria-pressed="at === 'complaints'" @click="at !== 'complaints' && router.push('/complaints')">{{ t('nav.complaints') }}</button>
  </div>
</template>
