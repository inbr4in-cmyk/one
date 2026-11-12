<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiCard, UiCheck, UiPrompt } from '@/components/ui'
import { oldCrmApi, type AnnulMoney } from '@/api/oldCrm'
import { useToastStore } from '@/stores/toast'
import { money } from '@/utils/dates'
import { apiErr } from '@/utils/err'
import type { Locale } from '@/i18n'

/** Owner's one-off: cancel the money balances that came over from the old CRM (preview first, then confirm). */
const { t, locale } = useI18n()
const loc = computed(() => locale.value as Locale)
const toast = useToastStore()
const info = ref<AnnulMoney | null>(null)
const debts = ref(false)
const busy = ref(false)
const ask = ref(false)
const count = computed(() => (info.value ? info.value.positive.students + (debts.value ? info.value.debts.students : 0) : 0))

async function check() {
  busy.value = true
  try { info.value = await oldCrmApi.annulMoney(false, false) } catch (e) { toast.error(apiErr(e) ?? t('errors.generic')) } finally { busy.value = false }
}
async function run() {
  busy.value = true
  try {
    const r = await oldCrmApi.annulMoney(debts.value, true)
    toast.ok(t('oldCrm.annul.done', { n: r.positive.students + (r.include_debts ? r.debts.students : 0) }))
    ask.value = false
    info.value = await oldCrmApi.annulMoney(false, false)
  } catch (e) { toast.error(apiErr(e) ?? t('errors.generic')) } finally { busy.value = false }
}
</script>

<template>
  <UiCard :title="t('oldCrm.annul.title')" class="oc-annul">
    <div v-if="info" class="oc-annul-r">
      <span>{{ t('oldCrm.annul.positive', { n: info.positive.students, sum: money(info.positive.sum, loc) }) }}</span>
      <span v-if="info.debts.students">{{ t('oldCrm.annul.debts', { n: info.debts.students, sum: money(info.debts.sum, loc) }) }}</span>
      <UiCheck v-if="info.debts.students" v-model="debts" :label="t('oldCrm.annul.includeDebts')" />
      <b v-if="!count">{{ t('oldCrm.annul.nothing') }}</b>
    </div>
    <div class="oc-annul-a">
      <UiButton :loading="busy && !ask" @click="check">{{ t('oldCrm.annul.check') }}</UiButton>
      <UiButton v-if="info && count" variant="primary" danger @click="ask = true">{{ t('oldCrm.annul.run') }}</UiButton>
    </div>
  </UiCard>
  <UiPrompt v-model:open="ask" :title="t('oldCrm.annul.title')" :text="t('oldCrm.annul.confirm', { n: count })"
    :confirm-label="t('oldCrm.annul.run')" danger :busy="busy" @confirm="run" />
</template>

<style scoped>
.oc-annul { margin-top: 16px }
.muted { color: var(--muted); margin: 0 0 12px }
.oc-annul-r { display: grid; gap: 8px; margin-bottom: 12px }
.oc-annul-a { display: flex; gap: 8px; flex-wrap: wrap }
</style>
