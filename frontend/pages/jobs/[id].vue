<script setup lang="ts">
import type { Job } from '~/types/job'

const route = useRoute()
const { getJob } = useApi()

const job = ref<Job | null>(null)
const error = ref('')
let timer: ReturnType<typeof setInterval> | undefined

async function load() {
  try {
    job.value = await getJob(String(route.params.id))
    error.value = ''
    if (job.value && (job.value.status === 'queued' || job.value.status === 'running')) {
      // keep polling while NCBI runs
    } else if (timer) {
      clearInterval(timer)
    }
  } catch (e: unknown) {
    const err = e as { data?: { detail?: string }; message?: string }
    error.value = err.data?.detail || err.message || 'Could not load this job.'
    if (timer) clearInterval(timer)
  }
}

onMounted(() => {
  load()
  timer = setInterval(load, 5000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
})

function fmt(n: unknown): string {
  if (n === null || n === undefined || n === '') return '—'
  if (typeof n === 'number' && Math.abs(n) > 0 && Math.abs(n) < 0.001) return n.toExponential(1)
  return String(n)
}
</script>

<template>
  <main class="page">
    <p><NuxtLink to="/jobs">← All jobs</NuxtLink></p>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-else-if="!job">Loading job…</p>

    <template v-else>
      <h1>Job {{ job.id }}</h1>
      <p>
        <span class="status-pill" :class="`status-${job.status}`">{{ job.status }}</span>
        <span v-if="job.status === 'queued' || job.status === 'running'" style="margin-left: 10px; font-size: 14px; color: var(--muted);">
          NCBI is running — you can close this page. WhatsApp will notify you when it is done.
        </span>
      </p>

      <p v-if="job.question" style="font-size: 17px;">“{{ job.question }}”</p>
      <p v-if="job.error" class="error">{{ job.error }}</p>

      <div class="card">
        <h2 style="margin-top: 0;">Search</h2>
        <dl class="meta">
          <dt>Program</dt><dd>{{ job.program || '—' }}</dd>
          <dt>Database</dt><dd>{{ job.database || '—' }}</dd>
          <dt>Detected type</dt><dd>{{ job.detected_type || '—' }}</dd>
          <dt>Accession</dt><dd>{{ job.accession || '—' }}</dd>
          <dt>Organism filter</dt><dd>{{ job.organism_filter || 'none' }}</dd>
          <dt>WhatsApp</dt><dd>{{ job.whatsapp_status || 'not_sent' }}</dd>
        </dl>
        <p v-if="job.parameters?.rationale" style="font-size: 14px; margin-bottom: 0;">
          <strong>Why this search:</strong> {{ job.parameters.rationale }}
        </p>
      </div>

      <template v-if="job.hits && job.hits.length">
        <h2>Hits</h2>
        <table class="hits">
          <thead>
            <tr><th>Accession</th><th>Organism</th><th>Identity</th><th>Coverage</th><th>E-value</th><th>Class</th></tr>
          </thead>
          <tbody>
            <tr v-for="hit in job.hits" :key="hit.accession">
              <td>{{ hit.accession }}</td>
              <td>{{ hit.organism || '—' }}</td>
              <td>{{ fmt(hit.identity) }}<span v-if="hit.identity !== undefined">%</span></td>
              <td>{{ fmt(hit.query_coverage) }}<span v-if="hit.query_coverage !== undefined">%</span></td>
              <td>{{ fmt(hit.evalue) }}</td>
              <td :class="`class-${hit.classification}`">{{ hit.classification || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </template>
      <p v-else-if="job.status === 'done'">No hits parsed for this job.</p>

      <template v-if="job.summary">
        <h2>Summary</h2>
        <div class="card" style="background: #fff;">{{ job.summary }}</div>
      </template>

      <template v-if="job.step_log && job.step_log.length">
        <h2>Agent step log</h2>
        <p style="font-size: 14px; color: var(--muted);">Every decision the agent took, with its reason. Outcome: {{ job.outcome || '—' }} · Searches used: {{ job.searches_used ?? '—' }}</p>
        <table class="hits">
          <thead>
            <tr><th>#</th><th>Step</th><th>Observation</th><th>Decision</th><th>Reason</th></tr>
          </thead>
          <tbody>
            <tr v-for="entry in job.step_log" :key="entry.seq">
              <td>{{ entry.seq }}</td>
              <td>{{ entry.step }}<span v-if="entry.is_deviation" class="class-borderline"> (deviation)</span></td>
              <td>{{ entry.observation || '—' }}</td>
              <td>{{ entry.decision || '—' }}</td>
              <td>{{ entry.deviation_reason || entry.reason || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </template>

      <div class="notice">
        Results page is the source of truth. Program, database, and parameters above let you
        reproduce this search at NCBI. Your sequence was sent to NCBI's public BLAST service.
      </div>
    </template>
  </main>
</template>
