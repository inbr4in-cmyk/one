<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiCard, UiEmptyState, UiInput, UiPager, UiSelect, UiSkeleton } from '@/components/ui'
import { adminApi, type AuditRow } from '@/api/admin'
import { useRefsStore } from '@/stores/refs'
import { dmy, hm } from '@/utils/dates'
import type { Locale } from '@/i18n'

const LIMIT = 50
const ENTITIES = ['student', 'payment', 'lesson', 'group', 'lead', 'user', 'role', 'setting', 'rate', 'expense', 'payroll', 'complaint', 'document', 'book_movement', 'shop_order', 'shop_item', 'chat', 'task']
const { t, te, locale } = useI18n()
const refs = useRefsStore()
const loc = computed(() => locale.value as Locale)
const f = reactive({ entity: '', actor_id: 0, action: '', since: '' })
const offset = ref(0)
const page = ref<{ items: AuditRow[]; total: number } | null>(null)
const open = ref<number | null>(null)

const entityOptions = computed(() => [{ value: '', label: t('audit.anyEntity') }, ...ENTITIES.map((e) => ({ value: e, label: entityLabel(e) }))])
const actorOptions = computed(() => [{ value: 0, label: t('audit.anyone') }, ...refs.staff.map((s) => ({ value: s.id, label: s.full_name }))])
const entityLabel = (e: string) => (te(`audit.entity.${e}`) ? t(`audit.entity.${e}`) : e)

let seq = 0
async function load() {
  const my = ++seq
  page.value = null
  const r = await adminApi.audit({
    entity: f.entity || undefined, actor_id: f.actor_id || null, action: f.action.trim() || undefined,
    since: f.since ? new Date(`${f.since}T00:00:00`).toISOString() : undefined, limit: LIMIT, offset: offset.value,
  }).catch(() => ({ items: [], total: 0 }))
  if (my === seq) page.value = r
}
let timer: ReturnType<typeof setTimeout> | undefined
watch(() => ({ ...f }), () => {
  clearTimeout(timer)
  timer = setTimeout(() => (offset.value === 0 ? load() : (offset.value = 0)), 300)
}, { deep: true })
watch(offset, load)
onMounted(() => {
  refs.load()
  refs.loadStaff()
  load()
})
function reset() {
  Object.assign(f, { entity: '', actor_id: 0, action: '', since: '' })
}
const fmt = (v: unknown) => (v === null || v === undefined ? '∅' : typeof v === 'object' ? JSON.stringify(v) : String(v))
/** Changed keys: before → after */
function diff(r: AuditRow) {
  const keys = [...new Set([...Object.keys(r.before ?? {}), ...Object.keys(r.after ?? {})])]
  return keys.map((k) => ({ k, b: r.before?.[k], a: r.after?.[k], changed: JSON.stringify(r.before?.[k]) !== JSON.stringify(r.after?.[k]) }))
}
</script>

<template>
  <div class="ph"><div><h1>{{ t('nav.audit') }}</h1><p>{{ t('audit.subtitle') }}</p></div></div>
  <div class="toolbar audit-f">
    <UiSelect v-model="f.entity" :options="entityOptions" :label="t('audit.entityLabel')" />
    <UiSelect v-model="f.actor_id" :options="actorOptions" :label="t('audit.actor')" />
    <UiInput v-model="f.action" type="search" icon="search" :placeholder="t('audit.actionPh')" />
    <input v-model="f.since" type="date" class="inp day-inp" :aria-label="t('audit.since')" :title="t('audit.since')" />
    <UiButton v-if="f.entity || f.actor_id || f.action || f.since" size="sm" variant="ghost" @click="reset">{{ t('common.reset') }}</UiButton>
  </div>

  <UiCard flush>
    <div v-if="!page" class="card-pad"><UiSkeleton :lines="8" /></div>
    <UiEmptyState v-else-if="!page.items.length" icon="log" :title="t('audit.empty')" />
    <div v-else class="card-b">
      <div v-for="r in page.items" :key="r.id" class="audit-row">
        <button type="button" class="list-row" :aria-expanded="open === r.id" @click="open = open === r.id ? null : r.id">
          <span class="num audit-at">{{ dmy(r.at, loc) }}<br /><span class="muted">{{ hm(r.at, loc) }}</span></span>
          <div class="grow">
            <b><code class="audit-act">{{ r.action }}</code> · {{ entityLabel(r.entity) }}<template v-if="r.entity_id"> #{{ r.entity_id }}</template></b>
            <span>{{ r.actor_name ?? t('audit.system') }}<template v-if="r.branch_id"> · {{ refs.branchName(r.branch_id) }}</template><template v-if="r.note"> · {{ r.note }}</template><template v-if="r.ip"> · {{ r.ip }}</template></span>
          </div>
          <svg class="ico chev-ico" :class="{ up: open === r.id }" aria-hidden="true"><use href="#i-down" /></svg>
        </button>
        <div v-if="open === r.id" class="audit-diff">
          <p v-if="!diff(r).length" class="muted m0">{{ t('audit.noData') }}</p>
          <div v-for="d in diff(r)" :key="d.k" class="audit-kv" :class="{ changed: d.changed }">
            <span class="k">{{ d.k }}</span>
            <span class="v"><s v-if="d.b !== undefined && d.changed">{{ fmt(d.b) }}</s><template v-if="d.b !== undefined && d.changed"> → </template>{{ fmt(d.a ?? d.b) }}</span>
          </div>
        </div>
      </div>
    </div>
    <div v-if="page && page.total > LIMIT" class="card-pad"><UiPager v-model="offset" :total="page.total" :limit="LIMIT" /></div>
  </UiCard>
</template>
