<script setup lang="ts">
/** Demo build only: one-tap sign-in as each staff role, each with its own recorded data. */
import { ref } from 'vue'
import UiButton from '@/components/ui/UiButton.vue'
import { useAuthStore, type LoginStep } from '@/stores/auth'
import { DEMO_PHONES, DEMO_ROLES, type DemoRole } from './meta'

const emit = defineEmits<{ done: [step: LoginStep] }>()
const auth = useAuthStore()
const busy = ref<DemoRole | null>(null)

const phoneOf = (r: DemoRole) => Object.entries(DEMO_PHONES).find(([, v]) => v === r)?.[0] ?? ''

async function enter(r: DemoRole) {
  if (busy.value) return
  busy.value = r
  try {
    const { useRole } = await import('./server')
    await useRole(r)
    emit('done', await auth.login(phoneOf(r), 'demo'))
  } finally {
    busy.value = null
  }
}
</script>

<template>
  <div class="demo-login">
    <p class="demo-note">Демо-версия с примерными данными школы. Выберите, кем войти:</p>
    <div class="demo-roles">
      <div v-for="(r, i) in DEMO_ROLES" :key="r.role" class="demo-role">
        <UiButton :variant="i === 0 ? 'primary' : 'navy'" size="lg" block :loading="busy === r.role" @click="enter(r.role)">
          {{ r.label }}
        </UiButton>
        <span class="demo-who">{{ r.who }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.demo-login { display: grid; gap: 14px; margin-top: 4px }
.demo-note { margin: 0; color: var(--muted); font-size: 14px }
.demo-roles { display: grid; gap: 12px }
.demo-role { display: grid; gap: 4px }
.demo-who { font-size: 12.5px; color: var(--muted); text-align: center }
</style>
