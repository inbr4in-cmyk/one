<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiCard, UiIcon, UiInput, UiPrompt, UiSelect, UiSkeleton } from '@/components/ui'
import { userDocsApi, type UserDoc, type UserDocAccept } from '@/api/compliance'
import { chatsApi } from '@/api/chats'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import { dmy, hm } from '@/utils/dates'
import { apiErr } from '@/utils/err'
import type { Locale } from '@/i18n'

/** Settings: files for each kind of user (a staff role, parents, students) and the journal of who accepted them. */
const { t, locale } = useI18n()
const auth = useAuthStore()
const toast = useToastStore()
const loc = computed(() => locale.value as Locale)
const canEdit = computed(() => auth.can('settings.edit'))
const audiences = ref<{ code: string; name: string }[] | null>(null)
const docs = ref<UserDoc[]>([])
const max = ref(2)
const journal = ref<UserDocAccept[]>([])
const audience = ref('')
const title = ref('')
const fileEl = ref<HTMLInputElement | null>(null)
const busy = ref(false)
const removing = ref<UserDoc | null>(null)

const options = computed(() => (audiences.value ?? []).map((a) => {
  const n = docs.value.filter((d) => d.audience === a.code).length
  return { value: a.code, label: n ? `${a.name} · ${n}` : a.name }
}))
const mine = computed(() => docs.value.filter((d) => d.audience === audience.value))
const log = computed(() => journal.value.filter((j) => j.audience === audience.value))

async function load() {
  const r = await userDocsApi.list()
  audiences.value = r.audiences
  docs.value = r.docs
  max.value = r.max
  if (!audience.value) audience.value = r.audiences[0]?.code ?? ''
  journal.value = await userDocsApi.journal().catch(() => [])
}
onMounted(() => load().catch(() => (audiences.value = [])))

async function upload() {
  const f = fileEl.value?.files?.[0]
  if (!f) return toast.error(t('nv.udoc.pickFile'))
  busy.value = true
  try {
    const up = await chatsApi.upload(f)
    await userDocsApi.add({ audience: audience.value, title: title.value.trim() || f.name, file_key: up.key, file_name: f.name })
    title.value = ''
    if (fileEl.value) fileEl.value.value = ''
    toast.ok(t('common.saved'))
    await load()
  } catch (e) {
    toast.error(apiErr(e) ?? t('errors.generic'))
  } finally {
    busy.value = false
  }
}
async function remove() {
  const d = removing.value
  removing.value = null
  if (!d) return
  await userDocsApi.remove(d.id)
  await load()
}
</script>

<template>
  <UiCard :title="t('nv.udoc.title')">
    <UiSkeleton v-if="!audiences" :lines="4" />
    <div v-else class="stack">
      <UiSelect v-model="audience" :options="options" :label="t('nv.udoc.audience')" block />
      <div v-if="mine.length" class="udoc-list">
        <div v-for="d in mine" :key="d.id" class="udoc">
          <UiIcon name="file" :size="20" />
          <span class="grow"><b>{{ d.title }}</b><span class="muted">{{ d.file_name }} · {{ t('nv.udoc.acceptedN', { n: d.accepted ?? 0 }) }}</span></span>
          <a v-if="d.url" :href="d.url" target="_blank" rel="noopener" class="linkbtn">{{ t('nv.udoc.open') }}</a>
          <UiButton v-if="canEdit" size="sm" variant="ghost" danger icon="delete" :aria-label="t('common.remove')" :title="t('common.remove')" @click="removing = d" />
        </div>
      </div>
      <p v-else class="muted" style="margin: 0">{{ t('nv.udoc.none') }}</p>
      <form v-if="canEdit && mine.length < max" class="stack subform" @submit.prevent="upload">
        <UiInput v-model="title" :label="t('nv.udoc.name')" :maxlength="255" />
        <input ref="fileEl" type="file" class="inp" accept=".pdf,.doc,.docx,.jpg,.jpeg,.png" :aria-label="t('nv.udoc.file')" />
        <div><UiButton type="submit" variant="navy" icon="plus" :loading="busy">{{ t('nv.udoc.add') }}</UiButton></div>
      </form>
      <template v-if="log.length">
        <b>{{ t('nv.udoc.journal') }}</b>
        <div class="scroll-x">
          <table class="tbl">
            <thead><tr><th scope="col">{{ t('nv.udoc.who') }}</th><th scope="col">{{ t('nv.udoc.file') }}</th><th scope="col">{{ t('nv.udoc.when') }}</th></tr></thead>
            <tbody>
              <tr v-for="j in log" :key="j.id">
                <td>{{ j.user_name }}</td>
                <td>{{ j.title }}<span v-if="j.removed" class="muted"> · {{ t('nv.udoc.removed') }}</span></td>
                <td class="num">{{ dmy(j.accepted_at, loc) }} {{ hm(j.accepted_at, loc) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </div>
  </UiCard>
  <UiPrompt :open="removing !== null" :title="t('nv.udoc.removeTitle')" :text="removing?.title ?? ''" :confirm-label="t('common.remove')" danger @update:open="(v) => !v && (removing = null)" @confirm="remove" />
</template>
