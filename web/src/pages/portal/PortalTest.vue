<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import TestRunner, { type RunnerApi } from '@/components/tests/TestRunner.vue'
import { myTestsApi } from '@/api/assessment'
import { usePortalStore } from '@/stores/portal'

/** A group test taken by the student at the lesson (the teacher starts it and restores an annulled attempt). */
const route = useRoute()
const portal = usePortalStore()
const id = computed(() => Number(route.params.id))
const ready = ref(false)
const sid = () => portal.child?.id ?? 0
const api: RunnerApi = {
  state: () => (sid() ? myTestsApi.state(id.value, sid()) : Promise.reject(new Error('no student'))),
  begin: () => myTestsApi.begin(id.value, sid()),
  answer: (question_id, answer) => myTestsApi.answer(id.value, { student_id: sid(), question_id, answer }),
  save: (part_id, answers, final) => myTestsApi.save(id.value, { student_id: sid(), part_id, answers, final }),
  video: (qid, file) => myTestsApi.video(id.value, sid(), qid, file),
  leave: () => myTestsApi.leave(id.value, sid()),
}
onMounted(async () => {
  if (!portal.me) await portal.load()
  ready.value = true
})
</script>

<template>
  <TestRunner v-if="ready" :api="api" exit-to="/portal/progress" />
</template>
