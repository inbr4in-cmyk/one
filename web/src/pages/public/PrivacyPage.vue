<script setup lang="ts">
import { computed, ref, watchEffect } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import BrandLogo from '@/components/layout/BrandLogo.vue'
import { UiSegmented } from '@/components/ui'
import { PRIVACY, SUPPORT, type PrivacyLang } from './privacy'

/** /privacy and /support: public pages, no login. ?lang=en opens them in English for the app stores. */
const { locale } = useI18n()
const route = useRoute()
const asked = String(route.query.lang ?? '')
const lang = ref<PrivacyLang>(asked === 'en' || asked === 'kk' || asked === 'ru' ? asked : locale.value === 'kk' ? 'kk' : 'ru')
const doc = computed(() => (route.name === 'support' ? SUPPORT : PRIVACY)[lang.value])
const langs = [{ value: 'ru' as const, label: 'Русский' }, { value: 'kk' as const, label: 'Қазақша' }, { value: 'en' as const, label: 'English' }]
watchEffect(() => {
  document.title = `${doc.value.title} · One English`
})
</script>

<template>
  <div class="pt">
    <header class="pt-top"><BrandLogo :size="34" :tagline="false" /><span class="sp" /></header>
    <main class="pt-main pv">
      <UiSegmented v-model="lang" :options="langs" label="Language" size="sm" />
      <article class="card pv-card" :lang="lang">
        <h1>{{ doc.title }}</h1>
        <p class="muted pv-date">{{ doc.updated }}</p>
        <p>{{ doc.intro }}</p>
        <section v-for="s in doc.sections" :key="s.h">
          <h2>{{ s.h }}</h2>
          <ul v-if="s.ul"><li v-for="x in s.ul" :key="x">{{ x }}</li></ul>
          <p v-for="x in s.p ?? []" :key="x">{{ x }}</p>
        </section>
      </article>
    </main>
  </div>
</template>

<style scoped>
.pv { max-width: 760px }
.pv-card { margin-top: 14px; padding: 28px clamp(18px, 4vw, 36px); line-height: 1.6; font-size: 15px }
.pv-card h1 { font-family: var(--font-display); font-weight: 600; font-size: 24px; letter-spacing: -.02em; margin: 0 0 4px }
.pv-card h2 { font-size: 16px; margin: 22px 0 8px; color: var(--accent-ink) }
.pv-card p { margin: 0 0 10px }
.pv-card ul { margin: 0 0 10px; padding-left: 20px; display: grid; gap: 6px }
.pv-date { font-size: 13px }
</style>
