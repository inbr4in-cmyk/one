<script setup lang="ts">
import { nextTick, ref, useId, watch } from 'vue'
import UiField from './UiField.vue'
import UiIcon from './UiIcon.vue'
import { caretAfterDigits, formatNational, nationalDigits, toE164 } from '@/utils/phone'

/** v-model is E.164 (+7XXXXXXXXXX) once complete, '' while incomplete. The field shows +7 XXX XXX XX XX. */
defineProps<{
  label?: string
  hint?: string
  error?: string | null
  autofocus?: boolean
  disabled?: boolean
}>()
const model = defineModel<string>({ default: '' })
const id = useId()
const el = ref<HTMLInputElement | null>(null)
const shown = ref(formatNational(nationalDigits(model.value, true)))
/** The user typed "+" into an empty number: the next "7" is the country code, not a digit. */
let awaitCountry = false

watch(model, (v) => {
  // External resets (e.g. clearing the form)
  if (v !== toE164(nationalDigits(shown.value))) shown.value = formatNational(nationalDigits(v, true))
})

function onInput(e: Event) {
  const input = e.target as HTMLInputElement
  const kind = (e as InputEvent).inputType ?? ''
  const whole = kind === 'insertFromPaste' || kind === 'insertReplacementText' || kind === '' || kind === 'insertFromDrop'
  const caret = input.selectionStart ?? input.value.length
  const digitsBeforeCaret = nationalDigits(input.value.slice(0, caret)).length
  let digits = nationalDigits(input.value, whole)

  const rest = input.value.replace(/^\+7\s?/, '').trim()
  if (!whole && rest === '+') awaitCountry = true
  else if (awaitCountry && digits === '7') {
    digits = ''
    awaitCountry = false
  } else awaitCountry = false

  const formatted = formatNational(digits) || '+7 '
  shown.value = formatted
  input.value = formatted
  model.value = toE164(digits)
  nextTick(() => {
    if (document.activeElement !== input) return
    const pos = caretAfterDigits(formatted, Math.min(digitsBeforeCaret, digits.length))
    input.setSelectionRange(pos, pos)
  })
}

function onFocus() {
  if (!shown.value) shown.value = '+7 '
}
function onBlur() {
  if (shown.value.trim() === '+7') shown.value = ''
}

defineExpose({ focus: () => el.value?.focus() })
</script>

<template>
  <UiField :label="label" :hint="hint" :error="error" :for="id">
    <div class="inp" :class="{ invalid: !!error, disabled }">
      <UiIcon name="phone" :size="18" />
      <input
        :id="id"
        ref="el"
        :value="shown"
        type="tel"
        inputmode="tel"
        autocomplete="tel"
        placeholder="+7 7__ ___ __ __"
        :autofocus="autofocus"
        :disabled="disabled"
        :aria-invalid="!!error || undefined"
        @input="onInput"
        @focus="onFocus"
        @blur="onBlur"
      />
    </div>
  </UiField>
</template>
