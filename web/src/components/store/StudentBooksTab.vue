<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { UiButton, UiCard, UiEmptyState, UiSkeleton } from '@/components/ui'
import SellBookModal from './SellBookModal.vue'
import { booksApi, type StudentBooks } from '@/api/store'
import { useAuthStore } from '@/stores/auth'
import { dmy, money } from '@/utils/dates'
import type { Locale } from '@/i18n'

/** Books tab on the student card: the book their level still needs, purchases, and selling one. */
const props = defineProps<{ student: { id: number; full_name: string; branch_id: number } }>()
const emit = defineEmits<{ sold: [] }>()
const { t, locale } = useI18n()
const auth = useAuthStore()
const loc = computed(() => locale.value as Locale)
const data = ref<StudentBooks | null>(null)
const selling = ref(false)

async function load() {
  data.value = await booksApi.ofStudent(props.student.id).catch(() => ({ items: [], needed: [] }))
}
onMounted(load)
function sold() {
  load()
  emit('sold')
}
</script>

<template>
  <div>
    <div class="grid fin-a">
      <UiCard :title="t('books.purchased')">
        <template v-if="auth.can('books.sell')" #actions><UiButton size="sm" variant="primary" icon="book" @click="selling = true">{{ t('books.sell') }}</UiButton></template>
        <UiSkeleton v-if="!data" :lines="3" />
        <UiEmptyState v-else-if="!data.items.length" icon="book" :title="t('books.noPurchases')" />
        <div v-for="(b, i) in data?.items ?? []" :key="i" class="list-row">
          <div class="grow"><b>{{ b.title }}</b><span>{{ dmy(b.at, loc) }} · × {{ b.qty }}</span></div>
          <b class="num">{{ money(b.price * b.qty, loc) }}</b>
        </div>
      </UiCard>
      <UiCard :title="t('books.needed')">
        <UiSkeleton v-if="!data" :lines="2" />
        <p v-else-if="!data.needed.length" class="muted m0">{{ t('books.nothingNeeded') }}</p>
        <div v-for="b in data?.needed ?? []" :key="b.id" class="list-row">
          <div class="grow"><b>{{ b.title }}</b><span>{{ money(b.price, loc) }}</span></div>
          <UiButton v-if="auth.can('books.sell')" size="sm" @click="selling = true">{{ t('books.sell') }}</UiButton>
        </div>
      </UiCard>
    </div>
    <SellBookModal v-model:open="selling" :student="student" :needed-ids="data?.needed.map((b) => b.id)" @sold="sold" />
  </div>
</template>
