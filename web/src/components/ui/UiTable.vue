<script setup lang="ts" generic="Row extends Record<string, unknown>">
import UiSkeleton from './UiSkeleton.vue'
import type { TableColumn as Column } from './types'

const props = withDefaults(defineProps<{
  columns: Column[]
  rows: Row[]
  /** Field used as the row key; defaults to `id`. */
  rowKey?: string
  loading?: boolean
  skeletonRows?: number
  hover?: boolean
}>(), { rowKey: 'id', skeletonRows: 4 })

const alignCls = (c: Column) => (c.align === 'right' ? 'r' : c.align === 'center' ? 'c' : undefined)
</script>

<template>
  <div class="scroll-x">
    <table class="tbl" :class="{ hover: props.hover }">
      <thead>
        <tr><th v-for="c in columns" :key="c.key" :class="alignCls(c)" :style="c.width ? { width: c.width } : undefined" scope="col">{{ c.label }}</th></tr>
      </thead>
      <tbody>
        <template v-if="loading">
          <tr v-for="i in skeletonRows" :key="`sk${i}`"><td v-for="c in columns" :key="c.key"><UiSkeleton :width="`${50 + ((i * 17) % 40)}%`" /></td></tr>
        </template>
        <template v-else>
          <tr v-for="(row, i) in rows" :key="String(row[rowKey] ?? i)">
            <td v-for="c in columns" :key="c.key" :class="alignCls(c)">
              <slot :name="`cell-${c.key}`" :row="row" :value="row[c.key]">{{ row[c.key] }}</slot>
            </td>
          </tr>
        </template>
      </tbody>
    </table>
    <slot v-if="!loading && !rows.length" name="empty" />
  </div>
</template>
