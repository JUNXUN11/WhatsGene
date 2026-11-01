<script setup lang="ts">
import type { Job } from '~/types/job'

definePageMeta({ middleware: 'auth' })

const { listJobs, cancelJob, deleteJob } = useApi()
const { push } = useToasts()
const jobs = ref<Job[]>([])
const error = ref('')
const confirmingDelete = ref<string | null>(null)
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

async function remove(id: string) {
  try {
    await deleteJob(id)
    jobs.value = jobs.value.filter(j => j.id !== id)
    confirmingDelete.value = null
    push({ kind: 'info', title: `Workflow ${id} deleted` }, 5000)
  } catch (e: unknown) {
    const err = e as { data?: { detail?: string }; message?: string }
    error.value = err.data?.detail || err.message || 'Could not delete this job.'
    confirmingDelete.value = null
  }
}

function isActive(job: Job) {
  return job.status === 'queued' || job.status === 'running'
}

function currentStep(job: Job): string | null {
  const log = job.step_log
  if (!log || !log.length) return null
  const latest = log[log.length - 1]
  return latest.decision ? `${latest.step} — ${latest.decision}` : latest.step
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
    <nav class="crumbs" aria-label="Breadcrumb"><NuxtLink to="/">Home</NuxtLink><span class="sep">/</span><span>Workflows</span></nav>
    <div class="page-head">
      <h1>Workflows</h1>
      <NuxtLink to="/new" class="btn">+ New search</NuxtLink>
    </div>
    <p class="lede">Every queued, running and finished search. Statuses refresh live — a notification pops up here when each one finishes.</p>

    <div v-if="!error && jobs.length" class="toolbar">
      <span class="toolbar-count">{{ jobs.length }} workflow{{ jobs.length === 1 ? '' : 's' }} · auto-refreshing every 5s</span>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <div v-else-if="!jobs.length" class="empty-state">
      <h2>No workflows yet</h2>
      <p>Run your first search — paste an accession or sequence and ask your question in plain words.</p>
      <NuxtLink to="/new" class="btn">Run your first search →</NuxtLink>
    </div>

    <div class="job-grid">
    <div v-for="job in jobs" :key="job.id" class="card job-card">
      <div class="job-top">
        <NuxtLink :to="`/jobs/${job.id}`" class="job-id">{{ job.id }}</NuxtLink>
        <span class="status-pill" :class="`status-${job.status}`">{{ job.status }}</span>
      </div>
      <p class="job-meta">{{ job.workflow_mode || 'auto' }} · {{ job.source || 'web' }}</p>
      <p v-if="job.question" class="job-question"><NuxtLink :to="`/jobs/${job.id}`">“{{ job.question }}”</NuxtLink></p>
      <p class="job-sub">
        {{ job.program || 'program pending' }} · {{ job.database || 'database pending' }}
        <span v-if="job.searches && job.searches.length"> · {{ job.searches.length }} search(es)</span>
      </p>
      <p v-if="isActive(job) && currentStep(job)" class="job-step"><strong>Current step:</strong> {{ currentStep(job) }}</p>
      <p v-if="job.status === 'done' && job.summary" class="job-summary">{{ job.summary }}</p>
      <p v-if="job.status === 'failed' && job.error" class="error">{{ job.error }}</p>
      <div class="job-actions">
        <button v-if="isActive(job)" class="btn btn-secondary btn-small" @click="cancel(job.id)">Cancel</button>
        <template v-else-if="confirmingDelete === job.id">
          <span class="confirm-text">Delete this workflow?</span>
          <button class="btn btn-danger btn-small" @click="remove(job.id)">Yes, delete</button>
          <button class="btn btn-secondary btn-small" @click="confirmingDelete = null">Keep</button>
        </template>
        <button v-else class="btn btn-secondary btn-small" @click="confirmingDelete = job.id">Delete</button>
      </div>
    </div>
    </div>
  </main>
</template>
