<script setup lang="ts">
import { computed, ref, useId } from 'vue'
import UiField from './UiField.vue'
import UiIcon from './UiIcon.vue'
import { useI18n } from 'vue-i18n'

const props = withDefaults(defineProps<{
  label?: string
  hint?: string
  error?: string | null
  type?: 'text' | 'password' | 'email' | 'search' | 'tel' | 'date' | 'time' | 'datetime-local' | 'number'
  icon?: string
  placeholder?: string
  autocomplete?: string
  inputmode?: 'text' | 'numeric' | 'tel' | 'email' | 'search'
  maxlength?: number
  min?: string | number
  max?: string | number
  disabled?: boolean
  required?: boolean
  autofocus?: boolean
  /** Big centered digits for one-time codes */
  code?: boolean
}>(), { type: 'text', error: null })

const model = defineModel<string>({ default: '' })
const id = useId()
const el = ref<HTMLInputElement | null>(null)
const reveal = ref(false)
const { t } = useI18n()

const actualType = computed(() => (props.type === 'password' && reveal.value ? 'text' : props.type))

defineExpose({ focus: () => el.value?.focus(), el })
</script>

<template>
  <UiField :label="label" :hint="hint" :error="error" :for="id">
    <div class="inp" :class="{ invalid: !!error, disabled, code }">
      <UiIcon v-if="icon" :name="icon" :size="18" />
      <input
        :id="id"
        ref="el"
        v-model="model"
        :type="actualType"
        :placeholder="placeholder"
        :autocomplete="autocomplete"
        :inputmode="inputmode"
        :maxlength="maxlength"
        :min="min"
        :max="max"
        :disabled="disabled"
        :required="required"
        :autofocus="autofocus"
        :aria-invalid="!!error || undefined"
      />
      <button
        v-if="type === 'password'"
        type="button"
        class="addon"
        :aria-label="reveal ? t('login.hidePassword') : t('login.showPassword')"
        :aria-pressed="reveal"
        @click="reveal = !reveal"
      >
        <UiIcon :name="reveal ? 'lock' : 'eye'" :size="18" />
      </button>
      <slot name="end" />
    </div>
  </UiField>
</template>
