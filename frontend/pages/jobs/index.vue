<script setup lang="ts">
import type { Job } from '~/types/job'

const { listJobs } = useApi()
const jobs = ref<Job[]>([])
const error = ref('')

onMounted(async () => {
  try {
    jobs.value = await listJobs()
  } catch (e: unknown) {
    const err = e as { message?: string }
    error.value = err.message || 'Could not load jobs. Is the backend running on port 8000?'
  }
})
</script>

<template>
  <main class="page">
    <h1>Recent jobs</h1>
    <p class="lede">Jobs you have submitted from this backend. Open one for status, hits, and the summary.</p>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-else-if="!jobs.length">No jobs yet. <NuxtLink to="/">Submit your first search</NuxtLink>.</p>

    <div v-for="job in jobs" :key="job.id" class="card" style="margin: 12px 0; padding: 16px 20px;">
      <NuxtLink :to="`/jobs/${job.id}`" style="font-weight: 700; text-decoration: none;">{{ job.id }}</NuxtLink>
      <span class="status-pill" :class="`status-${job.status}`" style="margin-left: 10px;">{{ job.status }}</span>
      <div style="font-size: 14px; color: var(--muted); margin-top: 6px;">
        {{ job.program || 'program pending' }} · {{ job.database || 'database pending' }}
        <span v-if="job.question"> · “{{ job.question }}”</span>
      </div>
    </div>
  </main>
</template>
