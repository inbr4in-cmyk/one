<script setup lang="ts">
import { computed, onMounted, ref, toRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { UiButton, UiCheck } from '@/components/ui'
import DocBody from './DocBody.vue'
import { docsApi, type DocumentVersion } from '@/api/compliance'
import { useAuthStore } from '@/stores/auth'
import { useDialog } from '@/composables/useDialog'
import { dmy } from '@/utils/dates'
import type { Locale } from '@/i18n'

/** Blocks the app until the current platform rules are accepted (when /auth/me lags behind the published version). */
const { t, locale } = useI18n()
const auth = useAuthStore()
const router = useRouter()
async function logout() {
  await auth.logout()
  router.replace({ name: 'login' })
}
const doc = ref<DocumentVersion | null>(null)
const agree = ref(false)
const busy = ref(false)
const box = ref<HTMLElement | null>(null)
const open = computed(() => !!doc.value && !!auth.user && auth.user.rules_accepted_version !== doc.value.version)
const { onKey } = useDialog(toRef(open), box, () => {})

onMounted(async () => {
  doc.value = await docsApi.get('rules').catch(() => null)
})

async function accept() {
  if (!doc.value || !agree.value) return
  busy.value = true
  try {
    const r = await docsApi.accept(doc.value.id)
    if (auth.user) auth.user.rules_accepted_version = r.version
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="open && doc" class="ov gate" @keydown="onKey">
        <div ref="box" class="dlg-box wide" role="alertdialog" aria-modal="true" aria-labelledby="gate-h" tabindex="-1">
          <header class="dlg-h"><h2 id="gate-h">{{ auth.user?.rules_accepted_version ? t('rules.updatedTitle') : t('rules.gateTitle') }}</h2></header>
          <div class="dlg-b">
            <p class="muted" style="margin-top: 0">{{ t('rules.gateText', { v: doc.version, date: dmy(doc.effective_from, locale as Locale) }) }}</p>
            <div class="doc-scroll"><h3 class="doc-title">{{ doc.title }}</h3><DocBody :body="doc.body" /></div>
          </div>
          <footer class="dlg-f gate-f">
            <UiCheck v-model="agree" :label="t('rules.agree')" />
            <span class="sp" />
            <UiButton variant="ghost" @click="logout">{{ t('user.logout') }}</UiButton>
            <UiButton variant="primary" :disabled="!agree" :loading="busy" @click="accept">{{ t('rules.accept') }}</UiButton>
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
