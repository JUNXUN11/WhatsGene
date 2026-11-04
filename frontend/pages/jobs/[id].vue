<script setup lang="ts">
import type { Job } from '~/types/job'

definePageMeta({ middleware: 'auth' })

const route = useRoute()
const router = useRouter()
const { getJob, cancelJob, deleteJob, askJob, alignJob } = useApi()
const { push } = useToasts()

const job = ref<Job | null>(null)
const error = ref('')
const askText = ref('')
const answer = ref('')
const answerSource = ref<'muse' | 'stored' | ''>('')
const asking = ref(false)
const aligning = ref(false)
const alignError = ref('')
const confirmingDelete = ref(false)
const POLL_SECONDS = 5
const countdown = ref(POLL_SECONDS)
const now = ref(new Date())
let timer: ReturnType<typeof setInterval> | undefined
let clock: ReturnType<typeof setInterval> | undefined

function stopTimers() {
  if (timer) clearInterval(timer)
  if (clock) clearInterval(clock)
  timer = undefined
  clock = undefined
}

async function load() {
  countdown.value = POLL_SECONDS
  try {
    job.value = await getJob(String(route.params.id))
    error.value = ''
    if (job.value && !isActive(job.value)) stopTimers()
  } catch (e: unknown) {
    const err = e as { data?: { detail?: string }; message?: string }
    error.value = err.data?.detail || err.message || 'Could not load this job.'
    stopTimers()
  }
}

onMounted(() => {
  load()
  timer = setInterval(load, POLL_SECONDS * 1000)
  clock = setInterval(() => {
    now.value = new Date()
    if (countdown.value > 0) countdown.value -= 1
  }, 1000)
})
onUnmounted(stopTimers)

function fmtDateTime(s?: string | null): string {
  if (!s) return '—'
  const d = new Date(s)
  if (Number.isNaN(d.getTime())) return s
  return d.toLocaleString()
}

function fmtClock(d: Date): string {
  return d.toLocaleTimeString()
}

function fmtElapsed(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) ms = 0
  const s = Math.floor(ms / 1000)
  const hh = String(Math.floor(s / 3600)).padStart(2, '0')
  const mm = String(Math.floor((s % 3600) / 60)).padStart(2, '0')
  const ss = String(s % 60).padStart(2, '0')
  return `${hh}:${mm}:${ss}`
}

const elapsed = computed(() => {
  const created = job.value?.created_at
  if (!created) return '—'
  const start = new Date(created).getTime()
  if (Number.isNaN(start)) return '—'
  return fmtElapsed(now.value.getTime() - start)
})

function isActive(j: Job) {
  return j.status === 'queued' || j.status === 'running'
}

function currentStep(): string | null {
  const log = job.value?.step_log
  if (!log || !log.length) return null
  const latest = log[log.length - 1]
  return latest.decision ? `${latest.step} — ${latest.decision}` : latest.step
}

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

async function remove() {
  if (!job.value) return
  try {
    await deleteJob(job.value.id)
    push({ kind: 'info', title: `Workflow ${job.value.id} deleted` }, 5000)
    await router.push('/jobs')
  } catch (e: unknown) {
    const err = e as { data?: { detail?: string }; message?: string }
    error.value = err.data?.detail || err.message || 'Could not delete this workflow.'
    confirmingDelete.value = false
  }
}

async function ask() {
  if (!job.value || !askText.value.trim()) return
  asking.value = true
  answer.value = ''
  answerSource.value = ''
  try {
    const res = await askJob(job.value.id, askText.value.trim())
    answer.value = res.answer
    answerSource.value = res.source
  } catch (e: unknown) {
    const err = e as { data?: { detail?: string }; message?: string }
    answer.value = err.data?.detail || err.message || 'Could not ask right now.'
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

const uniqueSearchNotes = computed(() => {
  const seen = new Set<string>()
  const notes: { key: string; program: string; reason: string; defaults: Record<string, unknown> | null }[] = []
  for (const s of job.value?.searches || []) {
    const reason = s.parameters?.short_query_reason
    if (!reason) continue
    const key = `${s.program || ''}:${reason}`
    if (seen.has(key)) continue
    seen.add(key)
    notes.push({
      key,
      program: s.program || 'search',
      reason: String(reason),
      defaults: (s.parameters?.ncbi_defaults as Record<string, unknown>) || null,
    })
  }
  return notes
})

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
    <nav class="crumbs" aria-label="Breadcrumb"><NuxtLink to="/jobs">Workflows</NuxtLink><span class="sep">/</span><span>{{ job ? workflowTitle(job) : route.params.id }}</span></nav>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-else-if="!job">Loading workflow…</p>

    <template v-else>
      <h1 class="detail-title">{{ workflowTitle(job) }}</h1>
      <p v-if="job.question" class="detail-input mono" :title="job.raw_input">{{ workflowInput(job) }}</p>
      <p class="job-headline">
        <span class="status-pill" :class="`status-${job.status}`">{{ job.status }}</span>
        <span class="headline-meta">
          {{ job.id }} · {{ job.workflow_mode || 'auto' }} workflow · from {{ job.source || 'web' }}
        </span>
        <span class="job-actions">
          <button v-if="isActive(job)" class="btn btn-secondary btn-small" @click="cancel">Cancel</button>
          <template v-else-if="confirmingDelete">
            <span class="confirm-text">Delete this workflow?</span>
            <button class="btn btn-danger btn-small" @click="remove">Yes, delete</button>
            <button class="btn btn-secondary btn-small" @click="confirmingDelete = false">Keep</button>
          </template>
          <button v-else class="btn btn-secondary btn-small" @click="confirmingDelete = true">Delete</button>
        </span>
      </p>

      <div v-if="isActive(job)" class="card status-card">
        <dl class="status-table">
          <div><dt>Workflow ID</dt><dd class="mono">{{ job.id }}</dd></div>
          <div><dt>Status</dt><dd><span class="status-pill" :class="`status-${job.status}`">{{ job.status === 'running' ? 'Calculating' : job.status }}</span></dd></div>
          <div><dt>Submitted at</dt><dd>{{ fmtDateTime(job.created_at) }}</dd></div>
          <div><dt>Current time</dt><dd>{{ fmtClock(now) }}</dd></div>
          <div><dt>Time since submission</dt><dd class="mono">{{ elapsed }}</dd></div>
        </dl>
        <p v-if="currentStep()" class="status-step"><strong>Current step:</strong> {{ currentStep() }}</p>
        <p v-else class="status-step">{{ job.status === 'queued' ? 'Waiting for a worker.' : 'Searching — NCBI queues can take a while.' }}</p>
        <div class="progress-strip" aria-hidden="true"><span /></div>
        <p class="hint status-refresh">This page will be automatically updated in {{ countdown }} second{{ countdown === 1 ? '' : 's' }}. You can leave — a notification pops up here when the run finishes.</p>
      </div>
      <p v-if="job.status === 'failed' && job.error" class="error">{{ job.error }}</p>

      <section v-if="job.status === 'done'" aria-label="Verdict" class="fade-in">
        <h2>Verdict</h2>
        <div class="card verdict">
          <div class="verdict-top">
            <span class="verdict-badge" :class="job.outcome ? `verdict-${job.outcome}` : ''">{{ job.outcome || 'finished' }}</span>
            <span class="headline-meta">{{ job.program || '—' }} / {{ job.database || '—' }}</span>
          </div>
          <p class="verdict-summary">{{ job.summary || 'No summary was recorded for this run.' }}</p>
          <dl v-if="job.hits && job.hits.length" class="stat-grid">
            <div><dt>Top hit</dt><dd>{{ job.hits[0].accession }}<span v-if="job.hits[0].organism"> · {{ job.hits[0].organism }}</span></dd></div>
            <div><dt>E-value</dt><dd>{{ fmt(job.hits[0].evalue) }}</dd></div>
            <div><dt>Identity</dt><dd>{{ fmt(job.hits[0].identity) }}%</dd></div>
            <div><dt>Coverage</dt><dd>{{ fmt(job.hits[0].query_coverage) }}%</dd></div>
            <div><dt>Class</dt><dd :class="`class-${job.hits[0].classification}`">{{ job.hits[0].classification || '—' }}</dd></div>
            <div><dt>Search</dt><dd>{{ job.program || '—' }} / {{ job.database || '—' }}</dd></div>
          </dl>
          <p v-else class="hint" style="margin-bottom: 0;">No hits were parsed for this run — see the step log below for what was tried.</p>
        </div>
      </section>

      <h2>Ask about this workflow</h2>
      <p class="hint">Answers quote stored E-values, parameters and hits only. If the stored results cannot answer, it will say so.</p>
      <div class="ask-card">
        <div class="sample-row" style="margin: 0 0 12px;">
          <button v-for="s in suggestions" :key="s" type="button" @click="askText = s">{{ s }}</button>
        </div>
        <form @submit.prevent="ask">
          <textarea v-model="askText" placeholder="What word size was used?" aria-label="Ask about this workflow" />
          <button class="btn" type="submit" :disabled="asking">{{ asking ? 'Asking…' : 'Ask →' }}</button>
        </form>
      </div>
      <div v-if="answer" class="answer-card">
        <p v-if="answerSource" class="answer-source">{{ answerSource === 'muse' ? 'Muse Spark — every number checked against the stored results' : 'From the stored results (add a Muse key in Settings for a written answer)' }}</p><div>{{ answer }}</div>
      </div>

      <template v-if="job.searches && job.searches.length">
        <h2>Searches in this workflow</h2>
        <p class="hint">Every BLAST run stores its exact parameters and hits, so programs compare value for value.</p>
        <div class="table-wrap">
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
        </div>
        <p v-for="n in uniqueSearchNotes" :key="n.key" style="font-size: 14px;">
          <strong>{{ n.program }}:</strong> {{ n.reason }}
          <span v-if="n.defaults"> NCBI defaults: E={{ fmt(n.defaults.evalue_threshold) }}, word={{ fmt(n.defaults.word_size) }}, matrix={{ fmt(n.defaults.matrix) }}.</span>
        </p>
      </template>

      <template v-if="job.hits && job.hits.length">
        <h2>All hits (primary search)</h2>
        <p class="hint">{{ job.hits.length }} hits — scroll inside the table, or narrow from the verdict above.</p>
        <div class="table-wrap table-scroll">
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
        </div>
      </template>

      <template v-if="job.status === 'done' || job.msa_alignment">
      <h2>Alignment and tree</h2>
      <p class="hint">From the confirmed homologs of this workflow: MAFFT alignment, then a neighbor-joining tree with Poisson-corrected distances after complete deletion of gap columns.</p>
      <button v-if="job.status === 'done' && !job.msa_alignment" class="btn" :disabled="aligning" @click="align">{{ aligning ? 'Aligning…' : 'Build MSA + tree' }}</button>
      <p v-if="job.status === 'done' && !job.msa_alignment" class="hint">{{ aligning ? 'Aligning — with the EBI service this takes 1–3 minutes; keep this page open.' : 'Uses MAFFT on this machine when installed (seconds). Otherwise the homolog sequences go to the MAFFT service at EBI, which takes 1–3 minutes.' }}</p>
      <p v-if="alignError" class="error">{{ alignError }}</p>
      <template v-if="job.msa_alignment">
        <p style="font-size: 14px;"><strong>Homologs:</strong> {{ (job.homologs || []).map(h => String(h.label)).join(', ') }}</p>
        <h3>Multiple sequence alignment</h3>
        <pre class="seqblock">{{ job.msa_alignment }}</pre>
        <h3>Neighbor-joining tree (Newick)</h3>
        <pre class="seqblock">{{ job.tree_newick }}</pre>
      </template>
      </template>

      <div class="card">
        <h2 style="margin-top: 0;">Search details</h2>
        <dl class="meta">
          <dt>Search backend</dt><dd>{{ job.parameters?.backend || job.backend_choice || '—' }}<span v-if="job.backend_choice"> (chosen: {{ job.backend_choice }})</span></dd>
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

      <template v-if="job.step_log && job.step_log.length">
        <h2>Agent step log</h2>
        <p class="hint">Every decision the agent took, with its reason.</p>
        <div class="table-wrap table-scroll">
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
        </div>
      </template>

      <div class="notice">
        {{ job.data_notice || 'Results page is the source of truth. Program, database, and parameters above let you reproduce this search.' }}
      </div>
    </template>
  </main>
</template>

<style scoped>
.seqblock {
  background: #141c26;
  color: #d5e0ee;
  border: 1px solid #141c26;
  border-radius: 10px;
  padding: 14px 16px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  line-height: 1.6;
  overflow-x: auto;
  white-space: pre;
}
</style>
