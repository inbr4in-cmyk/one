<script setup lang="ts">
// A dashboard number: the figure counts up when it appears or changes, the card lifts under the pointer.
import { onBeforeUnmount, ref, watch } from 'vue'
import { UiIcon } from '@/components/ui'

const props = defineProps<{ label: string; value: number; icon: string; tone?: 'navy' | 'ok' | 'red' | 'warn' | 'info'; hint?: string; lead?: boolean; suffix?: string; plain?: boolean }>()
defineEmits<{ open: [] }>()

const shown = ref(0)
let raf = 0
const calm = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches
function run(to: number) {
  cancelAnimationFrame(raf)
  const from = shown.value
  if (calm || from === to) return void (shown.value = to)
  const t0 = performance.now()
  const ms = 700
  const step = (t: number) => {
    const k = Math.min(1, (t - t0) / ms)
    shown.value = Math.round(from + (to - from) * (1 - Math.pow(1 - k, 3)))
    if (k < 1) raf = requestAnimationFrame(step)
  }
  raf = requestAnimationFrame(step)
}
watch(() => props.value, (v) => run(v ?? 0), { immediate: true })
onBeforeUnmount(() => cancelAnimationFrame(raf))
const fmt = (n: number) => (n < 0 ? '−' : '') + Math.abs(n).toLocaleString('ru-RU').replace(/,/g, ' ')
</script>

<template>
  <component :is="plain ? 'div' : 'button'" :type="plain ? undefined : 'button'" class="st" :class="[`t-${tone ?? 'navy'}`, { lead, plain }]" @click="!plain && $emit('open')">
    <span class="st-glow" aria-hidden="true" />
    <span class="st-top"><span class="st-ico"><UiIcon :name="icon" :size="20" /></span><UiIcon v-if="!plain" name="arrow" :size="16" class="st-go" /></span>
    <span class="st-v num">{{ fmt(shown) }}<small v-if="suffix">{{ suffix }}</small></span>
    <span class="st-k">{{ label }}</span>
    <span v-if="hint" class="st-h">{{ hint }}</span>
  </component>
</template>

<style scoped>
.st { --c: var(--navy-600); --bg: var(--navy-50); position: relative; overflow: hidden; display: grid; gap: 2px; text-align: left; font: inherit; color: var(--ink);
  background: var(--surface); border: 1px solid var(--line); border-radius: 18px; padding: 16px 18px 14px; cursor: pointer;
  transition: transform .28s cubic-bezier(.2,.8,.2,1), box-shadow .28s ease, border-color .2s ease }
.st.t-ok { --c: var(--ok); --bg: var(--ok-bg) } .st.t-red { --c: var(--red-ink); --bg: var(--red-100) }
.st.t-warn { --c: var(--warn); --bg: var(--warn-bg) } .st.t-info { --c: var(--info); --bg: var(--info-bg) }
.st::after { content: ''; position: absolute; left: 18px; right: 18px; bottom: 0; height: 3px; border-radius: 3px 3px 0 0; background: var(--c);
  transform: scaleX(.18); transform-origin: left; opacity: .55; transition: transform .45s cubic-bezier(.2,.8,.2,1), opacity .3s ease }
.st-glow { position: absolute; width: 150px; height: 150px; right: -56px; top: -64px; border-radius: 50%; background: var(--bg); transition: transform .5s cubic-bezier(.2,.8,.2,1) }
.st:hover, .st:focus-visible { transform: translateY(-4px); border-color: var(--c); box-shadow: 0 14px 30px -18px color-mix(in srgb, var(--c) 70%, transparent) }
.st:hover::after, .st:focus-visible::after { transform: scaleX(1); opacity: 1 }
.st:hover .st-glow { transform: scale(1.35) }
.st:active { transform: translateY(-1px) scale(.99) }
.st-top { position: relative; display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px }
.st-ico { width: 38px; height: 38px; display: grid; place-items: center; border-radius: 12px; background: var(--bg); color: var(--c); transition: transform .35s cubic-bezier(.2,.8,.2,1) }
.st:hover .st-ico { transform: rotate(-8deg) scale(1.08) }
.st-go { color: var(--c); opacity: 0; transform: translateX(-6px); transition: opacity .25s ease, transform .25s ease }
.st:hover .st-go, .st:focus-visible .st-go { opacity: 1; transform: none }
.st-v { position: relative; font-family: 'Unbounded'; font-weight: 600; font-size: 30px; letter-spacing: -.02em; line-height: 1.1 }
.st.plain { cursor: default }
.st-v small { font-size: .55em; font-weight: 500; margin-left: 4px }
.st-v { white-space: nowrap }
.st-k { position: relative; font-size: 13px; color: var(--muted) }
.st-k::first-letter { text-transform: uppercase }
.st-h { position: relative; font-size: 11.5px; color: var(--muted); opacity: .8 }
.st.lead { background: linear-gradient(135deg, var(--navy) 0%, var(--navy-600) 100%); border-color: transparent; color: #fff }
.st.lead .st-k, .st.lead .st-h { color: rgba(255, 255, 255, .78) }
.st.lead .st-ico { background: rgba(255, 255, 255, .16); color: #fff } .st.lead .st-glow { background: rgba(255, 255, 255, .09) }
.st.lead .st-go { color: #fff } .st.lead::after { background: var(--red) ; opacity: 1 }
@media (max-width: 640px) { .st { padding: 14px } .st-v { font-size: 24px } }
@media (prefers-reduced-motion: reduce) { .st, .st::after, .st-glow, .st-ico, .st-go { transition: none } .st:hover { transform: none } }
</style>
