<script setup lang="ts">
import { computed, onMounted, ref, toRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { UiButton, UiCheck, UiIcon } from '@/components/ui'
import { userDocsApi, type UserDoc } from '@/api/compliance'
import { useAuthStore } from '@/stores/auth'
import { useDialog } from '@/composables/useDialog'

/** Files the school set for my kind of user: shown once, until I accept them. */
const { t } = useI18n()
const auth = useAuthStore()
const router = useRouter()
const docs = ref<UserDoc[]>([])
const agree = ref(false)
const busy = ref(false)
const box = ref<HTMLElement | null>(null)
const open = computed(() => docs.value.length > 0)
const { onKey } = useDialog(toRef(open), box, () => {})

onMounted(async () => {
  docs.value = await userDocsApi.pending().catch(() => [])
})
async function logout() {
  await auth.logout()
  router.replace({ name: 'login' })
}
async function accept() {
  if (!agree.value) return
  busy.value = true
  try {
    await userDocsApi.accept(docs.value.map((d) => d.id))
    docs.value = []
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="open" class="ov gate" @keydown="onKey">
        <div ref="box" class="dlg-box" role="alertdialog" aria-modal="true" aria-labelledby="udoc-h" tabindex="-1">
          <header class="dlg-h"><h2 id="udoc-h">{{ t('nv.udoc.gateTitle') }}</h2></header>
          <div class="dlg-b">
            <div class="udoc-list">
              <a v-for="d in docs" :key="d.id" :href="d.url ?? undefined" target="_blank" rel="noopener" class="udoc">
                <UiIcon name="file" :size="20" /><span class="grow"><b>{{ d.title }}</b><span class="muted">{{ d.file_name }}</span></span>
                <span class="linkbtn">{{ t('nv.udoc.open') }}</span>
              </a>
            </div>
          </div>
          <footer class="dlg-f gate-f">
            <UiCheck v-model="agree" :label="t('nv.udoc.agree')" />
            <span class="sp" />
            <UiButton variant="ghost" @click="logout">{{ t('user.logout') }}</UiButton>
            <UiButton variant="primary" :disabled="!agree" :loading="busy" @click="accept">{{ t('nv.udoc.accept') }}</UiButton>
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
