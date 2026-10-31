<script setup lang="ts">
import type { Job } from '~/types/job'

const route = useRoute()
const { getJob, cancelJob, askJob, alignJob } = useApi()

const job = ref<Job | null>(null)
const error = ref('')
const askText = ref('')
const answer = ref('')
const asking = ref(false)
const aligning = ref(false)
const alignError = ref('')
let timer: ReturnType<typeof setInterval> | undefined

async function load() {
  try {
    job.value = await getJob(String(route.params.id))
    error.value = ''
    if (job.value && job.value.status !== 'queued' && job.value.status !== 'running' && timer) {
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

function fmtBool(v: unknown): string {
  return v === true ? 'yes' : 'no'
}

async function cancel() {
  if (!job.value) return
  await cancelJob(job.value.id)
  await load()
}

async function ask() {
  if (!job.value || !askText.value.trim()) return
  asking.value = true
  answer.value = ''
  try {
    answer.value = await askJob(job.value.id, askText.value.trim())
  } catch (e: unknown) {
    const err = e as { message?: string }
    answer.value = err.message || 'Could not ask right now.'
  } finally {
    asking.value = false
  }
}

async function align() {
  if (!job.value) return
  aligning.value = true
  alignError.value = ''
  try {
    job.value = await alignJob(job.value.id)
  } catch (e: unknown) {
    const err = e as { data?: { detail?: string }; message?: string }
    alignError.value = err.data?.detail || err.message || 'Alignment failed.'
  } finally {
    aligning.value = false
  }
}

const suggestions = [
  'What is the E-value cutoff?',
  'What is the word size?',
  'What is the scoring matrix? How does it compare to the defaults?',
  'Compare the programs — which found the best hit?',
  'How confident can I be in the top hit?',
]
</script>

<template>
  <main class="page">
    <p><NuxtLink to="/jobs">← All workflows</NuxtLink></p>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-else-if="!job">Loading workflow…</p>

    <template v-else>
      <h1>Job {{ job.id }}</h1>
      <p>
        <span class="status-pill" :class="`status-${job.status}`">{{ job.status }}</span>
        <span style="margin-left: 10px; font-size: 14px; color: var(--muted);">
          {{ job.workflow_mode || 'auto' }} workflow · started from {{ job.source || 'web' }}
          <template v-if="job.status === 'queued' || job.status === 'running'"> · running in the background — you can close this page<template v-if="job.notify_configured">; WhatsApp will notify you</template>.</template>
        </span>
        <button v-if="job.status === 'queued' || job.status === 'running'" class="btn btn-secondary" style="margin: 0 0 0 12px; padding: 6px 14px; font-size: 13px;" @click="cancel">Cancel</button>
      </p>

      <p v-if="job.question" style="font-size: 17px;">“{{ job.question }}”</p>
      <p v-if="job.error" class="error">{{ job.error }}</p>

      <div class="card">
        <h2 style="margin-top: 0;">Search</h2>
        <dl class="meta">
          <dt>Program</dt><dd>{{ job.program || '—' }}</dd>
          <dt>Database</dt><dd>{{ job.database || '—' }}</dd>
          <dt>Detected type</dt><dd>{{ job.detected_type || '—' }}<span v-if="job.query_length"> · {{ job.query_length }} residues</span></dd>
          <dt>Accession</dt><dd>{{ job.accession || '—' }}</dd>
          <dt>Organism filter</dt><dd>{{ job.organism_filter || 'none' }}</dd>
          <dt>WhatsApp notify</dt><dd>{{ job.whatsapp_status || 'not_sent' }}<span v-if="job.notify_configured"> (number stored server-side)</span></dd>
          <dt>Outcome</dt><dd>{{ job.outcome || '—' }} · searches used {{ job.searches_used ?? '—' }}</dd>
        </dl>
        <p v-if="job.parameters?.rationale" style="font-size: 14px; margin-bottom: 0;">
          <strong>Why this search:</strong> {{ job.parameters.rationale }}
        </p>
      </div>

      <template v-if="job.searches && job.searches.length">
        <h2>Searches in this workflow</h2>
        <p style="font-size: 14px; color: var(--muted);">Every BLAST run stores its exact parameters and hits, so programs can be compared value for value.</p>
        <table class="hits">
          <thead>
            <tr><th>Program</th><th>Database</th><th>Kind</th><th>E cutoff</th><th>Word</th><th>Matrix</th><th>Short-adj.</th><th>Hits</th><th>Top E-value</th><th>Status</th></tr>
          </thead>
          <tbody>
            <tr v-for="s in job.searches" :key="s.id">
              <td>{{ s.program || '—' }}</td>
              <td>{{ s.database || '—' }}</td>
              <td>{{ s.kind }}</td>
              <td>{{ fmt(s.parameters?.evalue_threshold) }}</td>
              <td>{{ fmt(s.parameters?.word_size) }}</td>
              <td>{{ fmt(s.parameters?.matrix) }}</td>
              <td>{{ fmtBool(s.parameters?.short_query_adjusted) }}</td>
              <td>{{ s.hits?.length ?? 0 }}</td>
              <td>{{ fmt(s.hits?.[0]?.evalue) }}</td>
              <td>{{ s.status }}<span v-if="s.error" class="error"> — {{ s.error }}</span></td>
            </tr>
          </tbody>
        </table>
        <template v-for="s in job.searches" :key="`note-${s.id}`">
          <p v-if="s.parameters?.short_query_reason" style="font-size: 14px;">
            <strong>{{ s.program }}:</strong> {{ s.parameters.short_query_reason }}
            <span v-if="s.parameters?.ncbi_defaults"> NCBI defaults: E={{ fmt((s.parameters.ncbi_defaults as Record<string, unknown>).evalue_threshold) }}, word={{ fmt((s.parameters.ncbi_defaults as Record<string, unknown>).word_size) }}, matrix={{ fmt((s.parameters.ncbi_defaults as Record<string, unknown>).matrix) }}.</span>
          </p>
        </template>
      </template>

      <template v-if="job.hits && job.hits.length">
        <h2>Hits (primary search)</h2>
        <table class="hits">
          <thead>
            <tr><th>Accession</th><th>Organism</th><th>Identity</th><th>Coverage</th><th>Bit score</th><th>E-value</th><th>Class</th><th>Taxa flag</th></tr>
          </thead>
          <tbody>
            <tr v-for="hit in job.hits" :key="hit.accession">
              <td>{{ hit.accession }}</td>
              <td>{{ hit.organism || '—' }}</td>
              <td>{{ fmt(hit.identity) }}<span v-if="hit.identity !== undefined">%</span></td>
              <td>{{ fmt(hit.query_coverage) }}<span v-if="hit.query_coverage !== undefined">%</span></td>
              <td>{{ fmt(hit.bit_score) }}</td>
              <td>{{ fmt(hit.evalue) }}</td>
              <td :class="`class-${hit.classification}`">{{ hit.classification || '—' }}</td>
              <td><span v-if="hit.taxa_flag" class="class-borderline">{{ hit.taxa_flag }}</span><span v-else>—</span></td>
            </tr>
          </tbody>
        </table>
      </template>
      <p v-else-if="job.status === 'done'">No hits parsed for this workflow.</p>

      <template v-if="job.summary">
        <h2>Summary</h2>
        <div class="card" style="background: #fff;">{{ job.summary }}</div>
      </template>

      <h2>Alignment and tree (Tier 2)</h2>
      <p style="font-size: 14px; color: var(--muted);">From the confirmed homologs of this workflow: MAFFT alignment (Lab 06), then a neighbor-joining tree with Poisson-corrected distances after complete deletion of gap columns (Lab 07). No bootstrapping — that stays roadmap-only.</p>
      <button v-if="job.status === 'done' && !job.msa_alignment" class="btn" :disabled="aligning" @click="align">{{ aligning ? 'Aligning…' : 'Build MSA + tree' }}</button>
      <p v-if="alignError" class="error">{{ alignError }}</p>
      <template v-if="job.msa_alignment">
        <p style="font-size: 14px;"><strong>Homologs:</strong> {{ (job.homologs || []).map(h => String(h.label)).join(', ') }}</p>
        <h3>Multiple sequence alignment</h3>
        <pre class="seqblock">{{ job.msa_alignment }}</pre>
        <h3>Neighbor-joining tree (Newick)</h3>
        <pre class="seqblock">{{ job.tree_newick }}</pre>
      </template>

      <h2>Ask about this workflow</h2>
      <p style="font-size: 14px; color: var(--muted);">Answers quote stored E-values, parameters and hits only. If the stored results cannot answer, it will say so. The same questions work on WhatsApp — include the job ID, e.g. “What was the E-value cutoff for {{ job.id }}?”</p>
      <div class="sample-row" style="margin-bottom: 10px;">
        <button v-for="s in suggestions" :key="s" type="button" @click="askText = s">{{ s }}</button>
      </div>
      <form @submit.prevent="ask">
        <textarea v-model="askText" style="min-height: 72px;" placeholder="What word size was used?" />
        <button class="btn" type="submit" :disabled="asking">{{ asking ? 'Asking…' : 'Ask' }}</button>
      </form>
      <div v-if="answer" class="card" style="background: #fff;">{{ answer }}</div>

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
        {{ job.data_notice || 'Results page is the source of truth. Program, database, and parameters above let you reproduce this search.' }}
      </div>
    </template>
  </main>
</template>

<style scoped>
.seqblock {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 12px;
  font-size: 12px;
  overflow-x: auto;
  white-space: pre;
}
</style>
