<script setup lang="ts">
import { ref, toRef, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import UiIcon from './UiIcon.vue'
import { useDialog } from '@/composables/useDialog'

const props = defineProps<{
  title?: string
  /** Slide in from the right instead of a centered dialog */
  drawer?: boolean
  wide?: boolean
}>()
const open = defineModel<boolean>('open', { required: true })
const box = ref<HTMLElement | null>(null)
const titleId = useId()
const { t } = useI18n()

const close = () => (open.value = false)
const { onKey } = useDialog(toRef(open), box, close)
</script>

<template>
  <Teleport to="body">
    <Transition :name="props.drawer ? 'drawer' : 'modal'">
      <div v-if="open" class="ov" :class="{ drawer: props.drawer }" @mousedown.self="close" @keydown="onKey">
        <div
          ref="box"
          class="dlg-box"
          :class="{ wide: props.wide }"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="props.title ? titleId : undefined"
          tabindex="-1"
        >
          <header v-if="props.title || $slots.header" class="dlg-h">
            <slot name="header"><h2 :id="titleId">{{ props.title }}</h2></slot>
            <button type="button" class="dlg-x" :aria-label="t('common.close')" @click="close"><UiIcon name="x" :size="18" /></button>
          </header>
          <div class="dlg-b"><slot /></div>
          <footer v-if="$slots.footer" class="dlg-f"><slot name="footer" :close="close" /></footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
