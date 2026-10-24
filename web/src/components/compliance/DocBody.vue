<script setup lang="ts">
import { computed } from 'vue'

/** Renders a document's plain-text body: `#` lines are headings, `-` lines are list items, blank lines split paragraphs. No HTML is interpreted. */
const props = defineProps<{ body: string }>()
type Block = { kind: 'h' | 'p' | 'ul'; text: string; items?: string[] }
const blocks = computed<Block[]>(() => {
  const out: Block[] = []
  for (const chunk of props.body.replace(/\r/g, '').split(/\n\s*\n/)) {
    const lines = chunk.split('\n').filter((l) => l.trim())
    if (!lines.length) continue
    if (lines.every((l) => /^\s*[-•*]\s+/.test(l))) {
      out.push({ kind: 'ul', text: '', items: lines.map((l) => l.replace(/^\s*[-•*]\s+/, '')) })
      continue
    }
    for (const [i, l] of lines.entries()) {
      if (/^#{1,6}\s/.test(l)) out.push({ kind: 'h', text: l.replace(/^#+\s*/, '') })
      else {
        out.push({ kind: 'p', text: lines.slice(i).join('\n') })
        break
      }
    }
  }
  return out
})
</script>

<template>
  <div class="doc-body">
    <template v-for="(b, i) in blocks" :key="i">
      <h3 v-if="b.kind === 'h'">{{ b.text }}</h3>
      <ul v-else-if="b.kind === 'ul'"><li v-for="(x, j) in b.items" :key="j">{{ x }}</li></ul>
      <p v-else>{{ b.text }}</p>
    </template>
  </div>
</template>
