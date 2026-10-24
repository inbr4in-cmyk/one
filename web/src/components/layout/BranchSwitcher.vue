<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useBranchStore } from '@/stores/branch'

const branch = useBranchStore()
const { t } = useI18n()
</script>

<template>
  <div class="branch" role="group" :aria-label="t('branch.label')">
    <button
      v-for="(o, i) in branch.options"
      :key="o.key"
      type="button"
      :class="{ wide: o.id === null || (branch.options.length % 2 === 1 && i === branch.options.length - 1) }"
      :aria-pressed="branch.current.key === o.key"
      @click="branch.select(o.id)"
    >
      {{ t(`branch.${o.key}`) }}
    </button>
  </div>
</template>
