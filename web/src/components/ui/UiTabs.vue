<script setup lang="ts" generic="T extends string">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{
  items: { value: T; label: string; count?: number }[]
  label?: string
}>()
const model = defineModel<T>({ required: true })

const root = ref<HTMLElement | null>(null)
const bar = ref({ x: 0, w: 0 })
let ro: ResizeObserver | null = null

function measure() {
  const el = root.value?.querySelector<HTMLElement>('button.on')
  if (el) bar.value = { x: el.offsetLeft, w: el.offsetWidth }
}

function onKey(e: KeyboardEvent) {
  if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
  const i = props.items.findIndex((it) => it.value === model.value)
  const next = props.items[(i + (e.key === 'ArrowRight' ? 1 : -1) + props.items.length) % props.items.length]
  if (!next) return
  model.value = next.value
  nextTick(() => root.value?.querySelector<HTMLElement>('button.on')?.focus())
}

watch(model, () => nextTick(measure))
watch(() => props.items, () => nextTick(measure), { deep: true })
onMounted(() => {
  measure()
  ro = new ResizeObserver(measure)
  if (root.value) ro.observe(root.value)
  document.fonts?.ready.then(measure).catch(() => {})
})
onBeforeUnmount(() => ro?.disconnect())
</script>

<template>
  <div ref="root" class="tabs" role="tablist" :aria-label="label" @keydown="onKey">
    <button
      v-for="it in items"
      :key="it.value"
      type="button"
      role="tab"
      :class="{ on: model === it.value }"
      :aria-selected="model === it.value"
      :tabindex="model === it.value ? 0 : -1"
      @click="model = it.value"
    >
      {{ it.label }}<span v-if="it.count !== undefined" class="n">{{ it.count }}</span>
    </button>
    <span class="bar" aria-hidden="true" :style="{ transform: `translateX(${bar.x}px) scaleX(${bar.w})` }" />
  </div>
</template>
