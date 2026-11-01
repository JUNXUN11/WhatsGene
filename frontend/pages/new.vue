<script setup lang="ts">
definePageMeta({ middleware: 'auth' })

const { createJob } = useApi()
const router = useRouter()
const route = useRoute()

const sequence = ref('')
const organism = ref('')
const question = ref('')
const mode = ref<'auto' | 'single' | 'all'>('auto')
const program = ref('blastp')
const whatsapp = ref('')
const searchBackend = ref<'server' | 'local' | 'ncbi'>('server')
const busy = ref(false)
const error = ref('')

const samples = [
  { label: 'Beta globin in nematodes', sequence: 'NP_000509', question: 'Is there a related gene in nematodes, and how confident can I be?' },
  { label: 'Insulin in C. elegans', sequence: 'NP_000198', question: 'Is there an insulin homolog in C. elegans?' },
  { label: '12-aa short query', sequence: 'PNLHGLFGRKTG', question: 'What is this short peptide?' },
]

onMounted(() => {
  const q = route.query
  if (typeof q.sequence === 'string' && q.sequence) sequence.value = q.sequence
  if (typeof q.question === 'string' && q.question) question.value = q.question
})

function useSample(s: (typeof samples)[number]) {
  sequence.value = s.sequence
  question.value = s.question
  error.value = ''
}

const progTabs = [
  { id: 'auto', label: 'Auto' },
  { id: 'blastn', label: 'blastn' },
  { id: 'blastp', label: 'blastp' },
  { id: 'blastx', label: 'blastx' },
  { id: 'tblastn', label: 'tblastn' },
  { id: 'tblastx', label: 'tblastx' },
  { id: 'all', label: 'All' },
]

function activeTab(): string {
  if (mode.value === 'auto') return 'auto'
  if (mode.value === 'all') return 'all'
  return program.value
}

function selectTab(id: string) {
  if (id === 'auto') mode.value = 'auto'
  else if (id === 'all') mode.value = 'all'
  else {
    mode.value = 'single'
    program.value = id
  }
  error.value = ''
}

function resetForm() {
  sequence.value = ''
  organism.value = ''
  question.value = ''
  mode.value = 'auto'
  program.value = 'blastp'
  whatsapp.value = ''
  searchBackend.value = 'server'
  error.value = ''
}

function fullQuestion(): string {
  const q = question.value.trim()
  const org = organism.value.trim()
  if (!org || q.toLowerCase().includes(org.toLowerCase())) return q
  return `${q.replace(/[?.!\s]+$/, '')} — look in ${org}`
}

async function submit() {
  error.value = ''
  if (!sequence.value.trim()) {
    error.value = 'Paste a sequence, FASTA, or an accession first.'
    return
  }
  busy.value = true
  try {
    const job = await createJob(sequence.value.trim(), fullQuestion(), {
      workflow_mode: mode.value,
      search_backend: searchBackend.value,
      program: mode.value === 'single' ? program.value : null,
      whatsapp_number: whatsapp.value.trim() || null,
    })
    await router.push(`/jobs/${job.id}`)
  } catch (e: unknown) {
    const err = e as { data?: { detail?: string }; message?: string }
    error.value = err.data?.detail || err.message || 'Could not queue this workflow. Is the backend running on port 8000?'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="page new-page">
    <nav class="crumbs" aria-label="Breadcrumb"><NuxtLink to="/">Home</NuxtLink><span class="sep">/</span><span>New search</span></nav>
    <h1>New search</h1>
    <p class="lede">Pick a program, fill in the panels, queue the run — the search finishes in the background.</p>

    <form @submit.prevent="submit">
      <div class="prog-tabs-block">
        <p class="prog-tabs-label">Program selection</p>
        <div class="prog-tabs" role="tablist" aria-label="BLAST program">
          <button
            v-for="t in progTabs"
            :key="t.id"
            type="button"
            role="tab"
            :aria-selected="activeTab() === t.id"
            :class="['prog-tab', { 'prog-tab-active': activeTab() === t.id }]"
            @click="selectTab(t.id)"
          >{{ t.label }}</button>
        </div>
        <p class="hint">
          <span v-if="mode === 'auto'"><strong>Auto</strong> — the rules engine picks the best program and database for your query type.</span>
          <span v-else-if="mode === 'all'"><strong>All</strong> — protein queries run blastp + tblastn; DNA queries run blastn + blastx + tblastx. Each stores its own parameters and hits for comparison.</span>
          <span v-else><strong class="mono">{{ program }}</strong> only — incompatible program/query pairs are rejected with the applicable list; nothing is submitted.</span>
        </p>
      </div>

      <div class="new-grid">
      <fieldset>
        <legend>Enter query sequence</legend>
        <label for="seq">Accession, FASTA, or raw sequence</label>
        <textarea id="seq" v-model="sequence" placeholder="NP_000509 — or paste FASTA / a raw sequence such as PNLHGLFGRKTG" />
        <div class="sample-row">
          <button v-for="s in samples" :key="s.label" type="button" @click="useSample(s)">{{ s.label }}</button>
        </div>
      </fieldset>

      <fieldset>
        <legend>Target and question</legend>
        <label for="org">Target organism or group (optional)</label>
        <input id="org" v-model="organism" type="text" placeholder="nematodes — or C. elegans, human, E. coli …">
        <p class="hint">Appended to your question so the rules engine limits the search to that group.</p>
        <label for="q">Your question</label>
        <input id="q" v-model="question" type="text" placeholder="Is there a related gene in nematodes?">
      </fieldset>

      <fieldset>
        <legend>Search options</legend>
        <label for="backend">Search on</label>
        <select id="backend" v-model="searchBackend" class="select">
          <option value="server">Server default (whatever this host is configured for)</option>
          <option value="local">Local BLAST — this server, Swiss-Prot, private</option>
          <option value="ncbi">Real NCBI BLAST — all programs and databases, slower</option>
        </select>
        <p v-if="searchBackend === 'local'" class="hint">Stays on this server; nothing is sent to NCBI.</p>
        <p v-if="searchBackend === 'ncbi'" class="hint">Your sequence is sent to NCBI's public BLAST service. Queues can take minutes to hours — the workflow runs in the background either way.</p>
        <details class="algo">
          <summary>Algorithm parameters</summary>
          <div class="algo-body">
            <p>Set automatically by the rules engine — you do not pick them by hand:</p>
            <ul>
              <li>Query type and length choose the program, database, E-value cutoff, word size and matrix.</li>
              <li>Short protein queries switch to the short-query profile on their own.</li>
              <li>Every search stores the exact values it ran with — see them quoted on the results page.</li>
            </ul>
          </div>
        </details>
      </fieldset>

      <fieldset>
        <legend>Notification (optional)</legend>
        <label for="wa">WhatsApp number for the done notification</label>
        <input id="wa" v-model="whatsapp" type="text" placeholder="e.g. 60123456789 — leave blank to just watch this page">
        <p class="hint">Stored server-side only, never shown on results pages. Outbound delivery is deferred (Meta verification), so watch here for now.</p>
      </fieldset>
      </div>

      <div class="submit-row">
        <button class="btn" type="submit" :disabled="busy">{{ busy ? 'Queueing…' : 'Run search →' }}</button>
        <button class="btn btn-secondary" type="button" :disabled="busy" @click="resetForm">Reset</button>
        <span class="hint">Queueing is instant. You will land on the live workflow page.</span>
      </div>
      <p v-if="error" class="error">{{ error }}</p>
    </form>
  </main>
</template>
