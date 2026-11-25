<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiEmptyState, UiModal, UiSelect, UiSkeleton } from '@/components/ui'
import { orgApi, type Level, type PlanRow } from '@/api/org'
import { useToastStore } from '@/stores/toast'
import { apiErr } from '@/utils/err'

/** «План» of a level: the lessons in order, by months. The teacher picks one of them when marking attendance. */
const props = defineProps<{ level: Level | null }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ saved: [number, number] }>()
const { t } = useI18n()
const toast = useToastStore()
type Row = { id: number | null; month: number; title: string; kind: PlanRow['kind']; key: number }
const rows = ref<Row[] | null>(null)
const busy = ref(false)
let seq = 0

watch(open, async (v) => {
  if (!v || !props.level) return
  rows.value = null
  const list = await orgApi.levelPlan(props.level.id).catch(() => [])
  rows.value = list.map((r) => ({ id: r.id, month: r.month, title: r.title, kind: r.kind, key: ++seq }))
})
const kinds = computed(() => (['lesson', 'progress_test', 'final_test'] as const).map((k) => ({ value: k, label: t(`nv.plan.kind.${k}`) })))
/** number inside the month, as in the school's plan */
const nums = computed(() => {
  const seen = new Map<number, number>()
  return (rows.value ?? []).map((r) => {
    seen.set(r.month, (seen.get(r.month) ?? 0) + 1)
    return seen.get(r.month)!
  })
})
function add() {
  const last = rows.value?.[rows.value.length - 1]
  rows.value = [...(rows.value ?? []), { id: null, month: last?.month ?? 1, title: '', kind: 'lesson', key: ++seq }]
}
function move(i: number, d: number) {
  const list = [...(rows.value ?? [])]
  const j = i + d
  if (j < 0 || j >= list.length) return
  ;[list[i], list[j]] = [list[j]!, list[i]!]
  rows.value = list
}
async function save() {
  if (!props.level || !rows.value) return
  if (rows.value.some((r) => !r.title.trim())) return toast.error(t('nv.plan.empty'))
  busy.value = true
  try {
    const saved = await orgApi.saveLevelPlan(props.level.id, rows.value.map((r) => ({ id: r.id, month: Math.max(1, Math.round(Number(r.month) || 1)), title: r.title.trim(), kind: r.kind })))
    emit('saved', props.level.id, saved.length)
    toast.ok(t('common.saved'))
    open.value = false
  } catch (e) {
    toast.error(apiErr(e) ?? t('errors.generic'))
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiModal v-model:open="open" wide :title="`${t('nv.plan.title')}: ${level?.name ?? ''}`">
    <UiSkeleton v-if="!rows" :lines="6" />
    <template v-else>
      <UiEmptyState v-if="!rows.length" icon="notebook" :title="t('nv.plan.none')" />
      <div v-else class="lp">
        <div class="lp-h"><span>{{ t('nv.plan.month') }}</span><span>№</span><span>{{ t('nv.plan.what') }}</span><span>{{ t('nv.plan.type') }}</span><span /></div>
        <div v-for="(r, i) in rows" :key="r.key" class="lp-r" :class="{ test: r.kind !== 'lesson', first: i === 0 || rows[i - 1]!.month !== r.month }">
          <input v-model.number="r.month" class="inp mini lp-m" type="number" min="1" max="24" :aria-label="t('nv.plan.month')" />
          <b class="num">{{ nums[i] }}</b>
          <input v-model="r.title" class="inp mini" maxlength="500" :aria-label="t('nv.plan.what')" />
          <UiSelect v-model="r.kind" :options="kinds" :label="t('nv.plan.type')" block />
          <span class="lp-a">
            <UiButton size="sm" variant="ghost" icon="up" :disabled="i === 0" :aria-label="t('nv.plan.up')" @click="move(i, -1)" />
            <UiButton size="sm" variant="ghost" icon="down" :disabled="i === rows.length - 1" :aria-label="t('nv.plan.down')" @click="move(i, 1)" />
            <UiButton size="sm" variant="ghost" icon="delete" :aria-label="t('common.remove')" @click="rows = rows.filter((x) => x.key !== r.key)" />
          </span>
        </div>
      </div>
      <UiButton icon="plus" style="margin-top: 12px" @click="add">{{ t('nv.plan.add') }}</UiButton>
    </template>
    <template #footer="{ close }">
      <span class="muted" style="margin-right: auto">{{ t('nv.plan.count', { n: rows?.length ?? 0 }) }}</span>
      <UiButton variant="ghost" @click="close">{{ t('common.cancel') }}</UiButton>
      <UiButton variant="primary" :loading="busy" :disabled="!rows" @click="save">{{ t('common.save') }}</UiButton>
    </template>
  </UiModal>
</template>

<style scoped>
.lp { display: grid; gap: 4px }
.lp-h, .lp-r { display: grid; grid-template-columns: 62px 28px minmax(0, 1fr) 160px 124px; gap: 10px; align-items: center }
.lp-h { font-size: 12px; color: var(--muted); padding: 0 2px 2px }
.lp-r.first:not(:first-of-type) { margin-top: 12px; padding-top: 12px; border-top: 1px dashed var(--line) }
.lp-r b { text-align: center; color: var(--muted) }
.lp-r .inp { width: 100%; height: 36px; color: var(--ink); font: inherit }
.lp-r.test input:not(.lp-m) { border-color: var(--red); font-weight: 600 }
.lp-a { display: inline-flex; gap: 0; justify-content: flex-end }
.lp-r > :nth-child(4) { min-width: 0; overflow: hidden }
@media (max-width: 700px) {
  .lp-h { display: none }
  .lp-r { grid-template-columns: 54px 24px minmax(0, 1fr); padding-bottom: 8px; border-bottom: 1px solid var(--line) }
  .lp-r > :nth-child(4) { grid-column: 1 / 3 }
  .lp-a { grid-column: 3 }
}
</style>
