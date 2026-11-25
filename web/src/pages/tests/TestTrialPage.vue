<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import TestRunner, { type RunnerApi } from '@/components/tests/TestRunner.vue'
import { trialApi, type TestOutline } from '@/api/assessment'

/** «Тестовый режим»: a staff member takes a staged test exactly as a student would; the result counts nowhere. */
const route = useRoute()
const testId = computed(() => Number(route.params.id))
const outline = ref<(TestOutline & { title: string }) | null>(null)
const failed = ref(false)
let attemptId = 0
const api: RunnerApi = {
  state: () => (attemptId ? trialApi.state(attemptId) : Promise.resolve(null)),
  begin: async () => {
    const s = await trialApi.begin(testId.value)
    attemptId = s.id
    return s
  },
  save: (part_id, answers, final) => trialApi.save(attemptId, { part_id, answers, final }),
  video: (qid, file) => trialApi.video(attemptId, qid, file),
  leave: () => trialApi.leave(attemptId),
  restore: () => trialApi.restore(attemptId),
}
onMounted(async () => {
  try {
    outline.value = await trialApi.outline(testId.value)
  } catch {
    failed.value = true
  }
})
</script>

<template>
  <TestRunner v-if="outline" :api="api" :title="outline.title" :outline="outline" exit-to="/tests" :result-to="(id) => `/tests/attempts/${id}`" />
  <p v-else-if="failed" style="padding: 40px; text-align: center"><RouterLink to="/tests">←</RouterLink></p>
</template>
