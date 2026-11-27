<script setup lang="ts">
// «Лиды по источникам» as tiles (owner picked variant 2, 27.11.2026): each source has its own icon and colour;
// the strip on top shows the shares, a tile opens the CRM filtered by that source.
import { computed, onMounted, ref } from 'vue'

const props = defineProps<{ items: { key: string; label: string; value: number; icon?: string; color?: string }[]; format?: (v: number) => string; plain?: boolean }>()
defineEmits<{ open: [key: string] }>()

const LOOK: Record<string, { icon: string; color: string; brand?: boolean }> = {
  instagram: { icon: 'instagram-color', color: '#D6286E', brand: true }, whatsapp: { icon: 'whatsapp-color', color: '#1FAF54', brand: true },
  referral: { icon: 'ref', color: '#C98A06' }, qr: { icon: 'qr-code', color: '#7B52C7' }, site: { icon: 'website', color: '#1560BD' },
  sales: { icon: 'phone', color: '#1A3F8A' }, walk_in: { icon: 'door', color: '#0E8FA8' }, return: { icon: 'lead-return', color: '#C8102E' },
  import: { icon: 'file', color: '#5B6782' },
}
// the school's own sources (Справочники) take the next colour of this row
const SPARE = ['#B4532A', '#2E9A6E', '#C2417F', '#4B5FD1', '#8A5D00', '#0B7A75']
const total = computed(() => props.items.reduce((n, x) => n + Math.max(0, x.value), 0))
const tiles = computed(() => {
  let spare = 0
  return props.items.map((x) => {
    const base = LOOK[x.key] ?? { icon: 'user', color: SPARE[spare++ % SPARE.length] as string }
    const look = { ...base, icon: x.icon ?? base.icon, color: x.color ?? base.color }
    return { ...x, ...look, brand: 'brand' in base && !x.icon ? base.brand : false, shown: props.format ? props.format(x.value) : String(x.value), pct: total.value ? Math.round((100 * x.value) / total.value) : 0 }
  })
})
const grown = ref(false)
onMounted(() => requestAnimationFrame(() => (grown.value = true)))
</script>

<template>
  <div class="src">
    <div class="src-strip" :class="{ grown }" aria-hidden="true"><i v-for="x in tiles" :key="x.key" :style="{ flexGrow: Math.max(0, x.value), background: x.color }" /></div>
    <div class="src-grid stagger">
      <component :is="plain ? 'div' : 'button'" v-for="x in tiles" :key="x.key" :type="plain ? undefined : 'button'" class="src-t" :class="{ plain, long: !!format }" :style="{ '--c': x.color }" @click="!plain && $emit('open', x.key)">
        <span class="src-top">
          <span class="src-ico" :class="{ 'src-full': x.brand }"><svg aria-hidden="true"><use :href="`#i-${x.icon}`" /></svg></span>
          <span class="src-pct num">{{ x.pct }}%</span>
        </span>
        <span class="src-v num">{{ x.shown }}</span>
        <span class="src-n">{{ x.label }}</span>
      </component>
    </div>
  </div>
</template>

<style scoped>
.src-strip { display: flex; gap: 4px; height: 12px; margin-bottom: 16px; transform: scaleX(0); transform-origin: left; transition: transform .8s cubic-bezier(.2,.8,.2,1) }
.src-strip.grown { transform: none }
.src-strip i { flex: 0 0 auto; flex-basis: 8px; border-radius: 6px }
.src-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px }
.src-t { position: relative; overflow: hidden; display: grid; gap: 2px; text-align: left; font: inherit; color: var(--ink); cursor: pointer; padding: 14px 14px 13px; border: 1px solid var(--line); border-radius: 16px;
  background: linear-gradient(160deg, color-mix(in srgb, var(--c) 9%, var(--surface)), var(--surface) 62%);
  transition: transform .28s cubic-bezier(.2,.8,.2,1), box-shadow .28s ease, border-color .2s ease }
.src-t::after { content: ''; position: absolute; left: 14px; right: 14px; bottom: 0; height: 3px; border-radius: 3px 3px 0 0; background: var(--c); transform: scaleX(.35); transform-origin: left; transition: transform .4s cubic-bezier(.2,.8,.2,1) }
.src-t:hover, .src-t:focus-visible { transform: translateY(-4px); border-color: var(--c); box-shadow: 0 14px 28px -18px var(--c) }
.src-t:hover::after, .src-t:focus-visible::after { transform: none }
.src-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px }
.src-ico { width: 36px; height: 36px; display: grid; place-items: center; border-radius: 11px; background: color-mix(in srgb, var(--c) 15%, var(--surface)); color: var(--c); transition: transform .35s cubic-bezier(.3,1.5,.5,1) }
.src-ico svg { width: 20px; height: 20px; fill: none; stroke: currentColor; stroke-width: 1.75; stroke-linecap: round; stroke-linejoin: round }
.src-ico.src-full { background: none } .src-ico.src-full svg { width: 36px; height: 36px; stroke: none }
.src-t:hover .src-ico { transform: scale(1.12) rotate(-6deg) }
.src-pct { font-size: 12px; font-weight: 700; color: var(--c); background: color-mix(in srgb, var(--c) 13%, var(--surface)); padding: 3px 8px; border-radius: 999px }
.src-v { font-family: 'Unbounded'; font-weight: 600; font-size: 24px; letter-spacing: -.02em; line-height: 1.15 }
.src-t.plain { cursor: default }
.src-t.long .src-v { font-size: 18px; white-space: nowrap }
.src-n { font-size: 13px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap }
@media (max-width: 640px) { .src-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px } .src-v { font-size: 20px } }
@media (prefers-reduced-motion: reduce) { .src-strip, .src-t, .src-t::after, .src-ico { transition: none } .src-strip { transform: none } .src-t:hover { transform: none } }
</style>
