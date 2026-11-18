<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiCard, UiChip, UiSkeleton } from '@/components/ui'
import { crmApi, type StageAccess, type StageLevel } from '@/api/crm'
import { useToastStore } from '@/stores/toast'

/** «Сотрудник × этап воронки»: the admin decides who sees and who edits leads on each stage. Saved cell by cell. */
const { t, te } = useI18n()
const toast = useToastStore()
const data = ref<StageAccess | null>(null)
const saving = ref<string | null>(null)

onMounted(async () => {
  data.value = await crmApi.stageAccess().catch(() => null)
})

const stageName = (s: { code: string; name: string }) => (te(`crm.stage.${s.code}`) ? t(`crm.stage.${s.code}`) : s.name)
const level = (u: number, s: number): StageLevel => data.value?.cells[`${u}:${s}`] ?? 'edit'

async function set(userId: number, stageId: number, value: StageLevel) {
  const d = data.value
  if (!d) return
  const key = `${userId}:${stageId}`
  const before = d.cells[key]
  saving.value = key
  if (value === 'edit') delete d.cells[key]
  else d.cells[key] = value
  try {
    await crmApi.setStageAccess(userId, stageId, value)
    toast.ok(t('common.saved'))
  } catch {
    if (before) d.cells[key] = before
    else delete d.cells[key]
  } finally {
    saving.value = null
  }
}
</script>

<template>
  <UiCard flush style="margin-top: 16px">
    <div class="card-pad" style="padding-bottom: 8px"><b>{{ t('nv.stageAccess.title') }}</b></div>
    <div v-if="!data" class="card-pad"><UiSkeleton :lines="4" /></div>
    <div v-else class="sa-wrap">
      <table class="sa">
        <thead>
          <tr><th>{{ t('nv.stageAccess.staff') }}</th><th v-for="s in data.stages" :key="s.id">{{ stageName(s) }}</th></tr>
        </thead>
        <tbody>
          <tr v-for="u in data.users" :key="u.id">
            <th scope="row"><b>{{ u.full_name }}</b><span>{{ u.roles.join(', ') }}</span></th>
            <td v-for="s in data.stages" :key="s.id">
              <UiChip v-if="u.locked" small tone="ok">{{ t('nv.stageAccess.full') }}</UiChip>
              <select v-else class="inp perm-sel" :class="level(u.id, s.id)" :value="level(u.id, s.id)" :disabled="saving === `${u.id}:${s.id}`" :aria-label="`${u.full_name}: ${stageName(s)}`" @change="set(u.id, s.id, ($event.target as HTMLSelectElement).value as StageLevel)">
                <option value="edit">{{ u.can_edit ? t('nv.stageAccess.edit') : t('nv.stageAccess.view') }}</option>
                <option value="own">{{ t('nv.stageAccess.own') }}</option>
                <option v-if="u.can_edit" value="view">{{ t('nv.stageAccess.view') }}</option>
                <option value="none">{{ t('nv.stageAccess.none') }}</option>
              </select>
            </td>
          </tr>
          <tr v-if="!data.users.length"><td :colspan="data.stages.length + 1" class="muted">{{ t('common.nothingFound') }}</td></tr>
        </tbody>
      </table>
    </div>
  </UiCard>
</template>

<style scoped>
.sa-wrap { overflow-x: auto; padding: 0 16px 16px }
.sa { border-collapse: collapse; width: 100%; font-size: 13px }
.sa th, .sa td { border-bottom: 1px solid var(--line); padding: 8px 8px; text-align: left; vertical-align: middle; white-space: nowrap }
.sa thead th { font-size: 12px; color: var(--muted); font-weight: 600 }
.sa tbody th { font-weight: 400; position: sticky; left: 0; background: var(--surface); min-width: 180px; white-space: normal }
.sa tbody th span { display: block; font-size: 12px; color: var(--muted) }
.sa select { min-width: 132px }
.sa select.own { background: var(--info-bg); color: var(--info) }
.sa select.view { background: var(--warn-bg); color: var(--warn) }
.sa select.none { background: var(--red-100); color: var(--red-ink) }
</style>
