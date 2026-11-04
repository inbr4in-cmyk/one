<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import UiIcon from '@/components/ui/UiIcon.vue'
import { THEMES, useUiStore, type ThemePref } from '@/stores/ui'

/**
 * Theme choice. `compact`: a row of round swatches (login screen, user menu).
 * Default: preview cards with names (profile / settings).
 */
const props = defineProps<{ compact?: boolean }>()
const ui = useUiStore()
const { t } = useI18n()
const root = ref<HTMLElement | null>(null)

const items = computed(() => THEMES.map((x) => ({ ...x, label: t(`theme.${x.id}`) })))

function pick(id: ThemePref) {
  ui.theme = id
}

/** Arrow keys move the choice, as in any radio group. */
function onKey(e: KeyboardEvent) {
  const step = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? -1 : 0
  if (!step) return
  e.preventDefault()
  const i = THEMES.findIndex((x) => x.id === ui.theme)
  const next = THEMES[(i + step + THEMES.length) % THEMES.length]
  if (!next) return
  pick(next.id)
  root.value?.querySelector<HTMLElement>(`[data-id="${next.id}"]`)?.focus()
}
</script>

<template>
  <div ref="root" class="theme-pick" :class="{ compact: props.compact }" role="radiogroup" :aria-label="t('theme.title')" @keydown="onKey">
    <button
      v-for="x in items"
      :key="x.id"
      type="button"
      role="radio"
      class="tp-it"
      :data-id="x.id"
      :aria-checked="ui.theme === x.id"
      :tabindex="ui.theme === x.id ? 0 : -1"
      :title="x.id === 'auto' ? `${x.label}: ${t('theme.autoHint')}` : x.label"
      :aria-label="props.compact ? x.label : undefined"
      @click="pick(x.id)"
    >
      <span
        class="tp-sw"
        :class="{ auto: x.id === 'auto' }"
        :style="{ '--p': x.swatch.paper, '--s': x.swatch.side, '--a': x.swatch.alt, '--k': x.swatch.accent, '--c': x.swatch.cta }"
        aria-hidden="true"
      >
        <template v-if="!props.compact">
          <i class="tp-side" /><i class="tp-card" /><i class="tp-cta" />
        </template>
        <UiIcon v-else-if="x.id === 'auto'" name="laptop" :size="14" />
      </span>
      <span v-if="!props.compact" class="tp-name">
        <b>{{ x.label }}</b>
        <small>{{ x.id === 'auto' ? t('theme.autoHint') : x.dark ? t('theme.isDark') : t('theme.isLight') }}</small>
      </span>
      <UiIcon v-if="!props.compact && ui.theme === x.id" name="ok" :size="16" class="tp-ok" />
    </button>
  </div>
</template>
