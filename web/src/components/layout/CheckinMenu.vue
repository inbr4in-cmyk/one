<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiIcon, UiSelect, UiTextarea } from '@/components/ui'
import { useClickOutside } from '@/composables/useClickOutside'
import { workApi, type MyCheckin } from '@/api/staffwork'
import { useAuthStore } from '@/stores/auth'
import { useRefsStore } from '@/stores/refs'
import { useToastStore } from '@/stores/toast'
import { hm, isoDate } from '@/utils/dates'
import { readPref, writePref } from '@/utils/storage'
import { apiErr } from '@/utils/err'
import type { Locale } from '@/i18n'

/** Topbar check-in / check-out and today's short report (Правила для сотрудников). */
const { t, locale } = useI18n()
const auth = useAuthStore()
const refs = useRefsStore()
const toast = useToastStore()
const open = ref(false)
const root = ref<HTMLElement | null>(null)
const me = ref<MyCheckin | null>(null)
const loaded = ref(false)
const branchId = ref(0)
const busy = ref(false)
const report = ref('')
const reportBusy = ref(false)
const reportErr = ref<string | null>(null)
useClickOutside([root], () => (open.value = false))

const draftKey = () => `oe.report.${auth.user?.id}.${isoDate(new Date())}`
const state = computed(() => (!me.value?.in_at ? 'none' : me.value.out_at ? 'out' : 'in'))
const branches = computed(() => (auth.user?.branch_ids ?? []).map((id) => ({ value: id, label: refs.branchName(id) })))
const label = computed(() => (state.value === 'in' ? t('checkin.since', { t: hm(me.value!.in_at!, locale.value as Locale) }) : state.value === 'out' ? t('checkin.done') : t('checkin.mark')))

async function load() {
  me.value = await workApi.me().catch(() => null)
  loaded.value = me.value !== null
}
onMounted(() => {
  refs.load()
  load()
  report.value = readPref(draftKey()) ?? ''
})
watch(open, (v) => {
  if (v) branchId.value = me.value?.branch_id ?? branches.value[0]?.value ?? 0
})
watch(report, (v) => writePref(draftKey(), v || null))

async function checkIn() {
  if (!branchId.value) return
  busy.value = true
  try {
    const r = await workApi.checkIn(branchId.value)
    me.value = { in_at: r.in_at, out_at: null, branch_id: branchId.value }
    toast.ok(t('checkin.inOk', { t: hm(r.in_at, locale.value as Locale) }))
  } finally {
    busy.value = false
  }
}
async function checkOut() {
  busy.value = true
  try {
    const r = await workApi.checkOut()
    me.value = { ...(me.value as MyCheckin), in_at: r.in_at, out_at: r.out_at }
    toast.ok(t('checkin.outOk', { t: hm(r.out_at, locale.value as Locale) }))
  } finally {
    busy.value = false
  }
}
async function sendReport() {
  reportErr.value = report.value.trim().length < 10 ? t('checkin.reportShort') : null
  if (reportErr.value) return
  reportBusy.value = true
  try {
    await workApi.report(report.value.trim())
    toast.ok(t('checkin.reportSaved'))
  } catch (e) {
    reportErr.value = apiErr(e) ?? t('errors.generic')
  } finally {
    reportBusy.value = false
  }
}
</script>

<template>
  <div v-if="loaded" ref="root" class="top-pop">
    <button type="button" class="checkin-btn" :class="state" :aria-expanded="open" aria-haspopup="true" @click="open = !open">
      <span class="ci-dot" aria-hidden="true" /><span class="ci-l">{{ label }}</span><UiIcon name="clock" :size="16" class="ci-ico" />
    </button>
    <Transition name="pop">
      <div v-if="open" class="menu checkin-pop" role="dialog" :aria-label="t('checkin.title')">
        <div class="stack">
          <div>
            <b>{{ t('checkin.title') }}</b>
            <p class="muted m0" style="font-size: 13px">
              <template v-if="state === 'none'">{{ t('checkin.notYet') }}</template>
              <template v-else-if="state === 'in'">{{ t('checkin.atWork', { t: hm(me!.in_at!, locale as Locale), b: refs.branchName(me!.branch_id) }) }}</template>
              <template v-else>{{ t('checkin.left', { from: hm(me!.in_at!, locale as Locale), to: hm(me!.out_at!, locale as Locale) }) }}</template>
            </p>
          </div>
          <template v-if="state === 'none'">
            <UiSelect v-if="branches.length > 1" v-model="branchId" :options="branches" :label="t('branch.label')" block />
            <UiButton variant="navy" icon="ok" :loading="busy" :disabled="!branchId" block @click="checkIn">{{ t('checkin.in') }}</UiButton>
          </template>
          <UiButton v-else-if="state === 'in'" icon="logout" :loading="busy" block @click="checkOut">{{ t('checkin.out') }}</UiButton>
          <hr class="sep" />
          <UiTextarea v-model="report" :label="t('checkin.report')" :placeholder="t('checkin.reportPh')" :rows="4" :maxlength="8000" :error="reportErr" />
          <UiButton size="sm" :loading="reportBusy" @click="sendReport">{{ t('checkin.reportSend') }}</UiButton>
          <p class="muted m0" style="font-size: 12px">{{ t('checkin.reportNote') }}</p>
        </div>
      </div>
    </Transition>
  </div>
</template>
