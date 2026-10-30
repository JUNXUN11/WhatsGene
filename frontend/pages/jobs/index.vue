<script setup lang="ts">
import type { Job } from '~/types/job'

const { listJobs, cancelJob } = useApi()
const jobs = ref<Job[]>([])
const error = ref('')
let timer: ReturnType<typeof setInterval> | undefined

async function load() {
  try {
    jobs.value = await listJobs()
    error.value = ''
  } catch (e: unknown) {
    const err = e as { message?: string }
    error.value = err.message || 'Could not load jobs. Is the backend running on port 8000?'
  }
}

async function cancel(id: string) {
  try {
    await cancelJob(id)
    await load()
  } catch (e: unknown) {
    const err = e as { message?: string }
    error.value = err.message || 'Could not cancel this job.'
  }
}

onMounted(() => {
  load()
  timer = setInterval(load, 5000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <main class="page">
    <h1>Workflows</h1>
    <p class="lede">Every queued, running and finished BLAST workflow. Queue several from the home page — they run in the background and WhatsApp you as each finishes.</p>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-else-if="!jobs.length">No workflows yet. <NuxtLink to="/">Queue your first search</NuxtLink>.</p>

    <div v-for="job in jobs" :key="job.id" class="card" style="margin: 12px 0; padding: 16px 20px;">
      <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
        <NuxtLink :to="`/jobs/${job.id}`" style="font-weight: 700; text-decoration: none;">{{ job.id }}</NuxtLink>
        <span class="status-pill" :class="`status-${job.status}`">{{ job.status }}</span>
        <span style="font-size: 13px; color: var(--muted);">{{ job.workflow_mode || 'auto' }} · {{ job.source || 'web' }}</span>
        <button v-if="job.status === 'queued' || job.status === 'running'" class="btn btn-secondary" style="margin: 0; padding: 6px 14px; font-size: 13px;" @click="cancel(job.id)">Cancel</button>
      </div>
      <div style="font-size: 14px; color: var(--muted); margin-top: 6px;">
        {{ job.program || 'program pending' }} · {{ job.database || 'database pending' }}
        <span v-if="job.searches && job.searches.length"> · {{ job.searches.length }} search(es) stored</span>
        <span v-if="job.question"> · “{{ job.question }}”</span>
      </div>
      <div v-if="job.summary" style="font-size: 14px; margin-top: 6px;">{{ job.summary }}</div>
    </div>
  </main>
</template>
