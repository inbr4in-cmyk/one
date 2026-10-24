<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

/**
 * One-series column chart in inline SVG (revenue by month). Bars are thin with 4px rounded tops on a
 * recessive grid; only the latest and the highest bars carry a value label, the rest show on hover.
 * A visually hidden table carries the same numbers for screen readers.
 */
const props = withDefaults(defineProps<{
  items: { key: string; label: string; value: number; soft?: boolean; note?: string }[]
  format: (v: number) => string
  /** Short axis label for a tick value */
  tick?: (v: number) => string
  caption: string
  height?: number
}>(), { height: 220 })

const root = ref<HTMLElement | null>(null)
const width = ref(560)
const hover = ref<number | null>(null)
let ro: ResizeObserver | null = null
onMounted(() => {
  ro = new ResizeObserver(([e]) => (width.value = Math.max(240, Math.round(e!.contentRect.width))))
  if (root.value) ro.observe(root.value)
})
onBeforeUnmount(() => ro?.disconnect())

function nice(max: number): number {
  if (max <= 0) return 1
  const p = 10 ** Math.floor(Math.log10(max))
  return ([1, 2, 2.5, 5, 10].find((m) => m * p >= max) ?? 10) * p
}
const top = computed(() => nice(Math.max(0, ...props.items.map((i) => i.value))))
const ticks = computed(() => [0, 0.25, 0.5, 0.75, 1].map((k) => k * top.value))
const tickText = (v: number) => (props.tick ? props.tick(v) : props.format(v))
/** Left padding fits the longest tick label (≈7px per glyph at 12px) */
const PAD = computed(() => ({ l: Math.max(32, Math.max(...ticks.value.map((v) => tickText(v).length)) * 7 + 14), r: 8, t: 22, b: 26 }))
const plotH = computed(() => props.height - PAD.value.t - PAD.value.b)
const step = computed(() => (width.value - PAD.value.l - PAD.value.r) / Math.max(1, props.items.length))
const barW = computed(() => Math.min(40, Math.max(10, step.value * 0.5)))
const y = (v: number) => PAD.value.t + plotH.value - (v / top.value) * plotH.value
const maxIdx = computed(() => props.items.reduce((b, it, i, a) => (it.value > a[b]!.value ? i : b), 0))
const bars = computed(() => props.items.map((it, i) => {
  const x = PAD.value.l + step.value * i + (step.value - barW.value) / 2
  const h = Math.max(it.value > 0 ? 2 : 0, (it.value / top.value) * plotH.value)
  const r = Math.min(4, barW.value / 2, h)
  const yTop = PAD.value.t + plotH.value - h
  const base = PAD.value.t + plotH.value
  // Rounded top corners only: the bar stays anchored to the baseline.
  const d = h <= 0 ? '' : `M${x},${base}V${yTop + r}Q${x},${yTop} ${x + r},${yTop}H${x + barW.value - r}Q${x + barW.value},${yTop} ${x + barW.value},${yTop + r}V${base}Z`
  return { ...it, i, x, cx: x + barW.value / 2, yTop, d, showValue: i === props.items.length - 1 || i === maxIdx.value }
}))
const tip = computed(() => (hover.value === null ? null : bars.value[hover.value] ?? null))
</script>

<template>
  <div ref="root" class="chart" @mouseleave="hover = null">
    <svg :width="width" :height="height" :viewBox="`0 0 ${width} ${height}`" role="img" :aria-label="caption">
      <g aria-hidden="true">
        <g v-for="v in ticks" :key="v">
          <line :x1="PAD.l" :x2="width - PAD.r" :y1="y(v)" :y2="y(v)" stroke="var(--grid)" stroke-width="1" />
          <text :x="PAD.l - 8" :y="y(v) + 4" text-anchor="end">{{ tick ? tick(v) : format(v) }}</text>
        </g>
        <g v-for="b in bars" :key="b.key">
          <path v-if="b.d" :d="b.d" :fill="b.soft ? 'var(--chart-bar-soft)' : 'var(--chart-bar)'" :opacity="hover === null || hover === b.i ? 1 : 0.55" />
          <text v-if="b.showValue && b.value > 0" :x="b.cx" :y="b.yTop - 6" text-anchor="middle" class="bar-v">{{ tick ? tick(b.value) : format(b.value) }}</text>
          <text :x="b.cx" :y="height - 8" text-anchor="middle">{{ b.label }}</text>
          <!-- hit target wider than the mark -->
          <rect :x="b.x - (step - barW) / 2" :y="PAD.t" :width="step" :height="plotH" fill="transparent" @mouseenter="hover = b.i" @focus="hover = b.i" />
        </g>
      </g>
    </svg>
    <div v-if="tip" class="chart-tip" :style="{ left: `${Math.min(Math.max(tip.cx, 70), width - 70)}px`, top: `${Math.max(tip.yTop - 8, 0)}px` }">
      <b>{{ format(tip.value) }}</b><span>{{ tip.label }}<template v-if="tip.note"> · {{ tip.note }}</template></span>
    </div>
    <table class="sr">
      <caption>{{ caption }}</caption>
      <tbody><tr v-for="it in items" :key="it.key"><th scope="row">{{ it.label }}</th><td>{{ format(it.value) }}</td></tr></tbody>
    </table>
  </div>
</template>
