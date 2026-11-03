<script setup lang="ts">
import type { LocalDatabase } from '~/composables/useApi'

definePageMeta({ middleware: 'auth' })

const { createJob, getSettings, listDatabases } = useApi()
const strictnessLabel = ref('')
const router = useRouter()
const route = useRoute()

const sequence = ref('')
const organism = ref('')
const question = ref('')
const mode = ref<'auto' | 'single' | 'all'>('auto')
const program = ref('blastp')
const whatsapp = ref('')
const searchBackend = ref<'server' | 'local' | 'ncbi'>('server')
const database = ref('')
const databases = ref<LocalDatabase[]>([])
const busy = ref(false)
const error = ref('')
const showSubmitConfirm = ref(false)
const showResetConfirm = ref(false)
// Sequence-first (decision: owner, 2 Nov): the query box is the whole form.
// Everything below it (target, program, backend, notify) is optional and
// starts collapsed; it opens when a link or sample carries a question.
const optionsOpen = ref(false)

const backendLabels: Record<string, string> = {
  server: 'Server default',
  local: 'Local BLAST (private, this server)',
  ncbi: 'Real NCBI BLAST (sequence leaves this server)',
}

const isDirty = computed(() => {
  return sequence.value.trim() !== ''
    || organism.value.trim() !== ''
    || question.value.trim() !== ''
    || mode.value !== 'auto'
    || program.value !== 'blastp'
    || whatsapp.value.trim() !== ''
    || searchBackend.value !== 'server'
    || database.value !== ''
})

const selectedDatabase = computed(() => databases.value.find(d => d.name === database.value) || null)
const databaseDisabled = computed(() => mode.value === 'all' || searchBackend.value === 'ncbi')
const databaseLabel = computed(() => selectedDatabase.value
  ? `${selectedDatabase.value.label} (${selectedDatabase.value.dbtype})`
  : 'Auto — WhatsGene chooses')

const modeLabel = computed(() => {
  if (mode.value === 'auto') return 'Auto (rules engine picks)'
  if (mode.value === 'all') return 'All programs'
  return program.value
})

function queryPreview(): string {
  const s = sequence.value.trim().replace(/\s+/g, ' ')
  return s.length > 90 ? `${s.slice(0, 90)}…` : s
}

const samples = [
  { label: 'Beta globin in nematodes', sequence: 'NP_000509', question: 'Is there a related gene in nematodes, and how confident can I be?' },
  { label: 'Insulin in C. elegans', sequence: 'NP_000198', question: 'Is there an insulin homolog in C. elegans?' },
  { label: '12-aa short query', sequence: 'PNLHGLFGRKTG', question: 'What is this short peptide?' },
]

onMounted(async () => {
  const q = route.query
  if (typeof q.sequence === 'string' && q.sequence) sequence.value = q.sequence
  if (typeof q.question === 'string' && q.question) {
    question.value = q.question
    optionsOpen.value = true
  }
  // Settings defaults pre-fill the form; anything typed or linked wins.
  try {
    const res = await getSettings()
    if (!organism.value && res.settings.default_organism) organism.value = res.settings.default_organism
    searchBackend.value = res.settings.default_backend
    strictnessLabel.value = res.presets[res.settings.strictness]?.label || res.settings.strictness
  } catch {
    // Defaults are a convenience; the form works with server defaults.
  }
  try {
    databases.value = await listDatabases()
    const wanted = route.query.database
    if (typeof wanted === 'string' && databases.value.some(d => d.name === wanted && d.ready)) {
      database.value = wanted
      optionsOpen.value = true
    }
  } catch {
    // The picker is optional; Auto still works without the catalog.
  }
})

watch([mode, searchBackend], () => {
  if (databaseDisabled.value) database.value = ''
})

function useSample(s: (typeof samples)[number]) {
  sequence.value = s.sequence
  question.value = s.question
  if (s.question) optionsOpen.value = true
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
  database.value = ''
  error.value = ''
  showResetConfirm.value = false
}

function askReset() {
  if (!isDirty.value) return
  showResetConfirm.value = true
}

function fullQuestion(): string {
  const q = question.value.trim()
  const org = organism.value.trim()
  if (!org || q.toLowerCase().includes(org.toLowerCase())) return q
  return `${q.replace(/[?.!\s]+$/, '')} — look in ${org}`
}

function submit() {
  error.value = ''
  if (!sequence.value.trim()) {
    error.value = 'Paste a sequence, FASTA, or an accession first.'
    return
  }
  showSubmitConfirm.value = true
}

async function confirmSubmit() {
  requestSystemNotifications() // this click is the gesture the prompt needs
  busy.value = true
  try {
    const job = await createJob(sequence.value.trim(), fullQuestion(), {
      workflow_mode: mode.value,
      search_backend: searchBackend.value,
      program: mode.value === 'single' ? program.value : null,
      database: databaseDisabled.value ? null : (database.value || null),
      whatsapp_number: whatsapp.value.trim() || null,
    })
    await router.push(`/jobs/${job.id}`)
  } catch (e: unknown) {
    const err = e as { data?: { detail?: string }; message?: string }
    error.value = err.data?.detail || err.message || 'Could not queue this workflow. Is the backend running on port 8000?'
    showSubmitConfirm.value = false
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="page new-page">
    <h1>New search</h1>
    <p class="lede">Paste a sequence or accession — WhatsGene picks the BLAST program, runs the search in the background, and classifies every hit for you. Add a target organism or a question only when you need a narrower answer.</p>

    <form @submit.prevent="submit">
      <fieldset>
        <legend>Enter query sequence</legend>
        <label for="seq">Accession, FASTA, or raw sequence</label>
        <textarea id="seq" v-model="sequence" placeholder="NP_000509 — or paste FASTA / a raw sequence such as PNLHGLFGRKTG" />
        <div class="sample-row">
          <button v-for="s in samples" :key="s.label" type="button" @click="useSample(s)">{{ s.label }}</button>
        </div>
      </fieldset>

      <div class="more-options">
        <button
          type="button"
          class="more-toggle"
          :aria-expanded="optionsOpen"
          aria-controls="more-options-body"
          @click="optionsOpen = !optionsOpen"
        >
          <span class="more-chevron" :class="{ 'more-chevron-open': optionsOpen }" aria-hidden="true">›</span>
          More options
          <span class="more-toggle-hint">target organism, question, program, backend</span>
        </button>
        <div v-show="optionsOpen" id="more-options-body" class="more-body">
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
          </div>

          <div class="new-grid">
          <fieldset>
            <legend>Target and question</legend>
            <label for="org">Target organism or group (optional)</label>
            <input id="org" v-model="organism" type="text" placeholder="nematodes — or C. elegans, human, E. coli …">
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
            <label for="database">Local database</label>
            <select id="database" v-model="database" class="select" :disabled="databaseDisabled">
              <option value="">Auto — WhatsGene chooses</option>
              <option v-for="db in databases" :key="db.name" :value="db.name" :disabled="!db.ready">
                {{ db.label }} ({{ db.dbtype }}){{ db.ready ? '' : ' — not built' }}
              </option>
            </select>
            <p v-if="selectedDatabase" class="hint">{{ selectedDatabase.description }}</p>
            <p v-else-if="databaseDisabled" class="hint">Database choice needs Auto or one program, on Local BLAST.</p>
            <p v-if="strictnessLabel" class="hint">Hit collection: {{ strictnessLabel }} — from <NuxtLink to="/settings">Settings</NuxtLink>, where you can also set your own judging cut-offs.</p>
          </fieldset>

          <fieldset>
            <legend>Notification (optional)</legend>
            <label for="wa">WhatsApp number for the done notification</label>
            <input id="wa" v-model="whatsapp" type="text" placeholder="e.g. 60123456789 — leave blank to just watch this page">
          </fieldset>
          </div>
        </div>
      </div>

      <div class="submit-row">
        <button class="btn" type="submit" :disabled="busy">Run search →</button>
        <button class="btn btn-secondary" type="button" :disabled="busy || !isDirty" @click="askReset">Reset</button>
      </div>
      <p v-if="error" class="error">{{ error }}</p>
    </form>

    <ConfirmDialog
      :open="showSubmitConfirm"
      title="Queue this search?"
      confirm-label="Queue search"
      :busy="busy"
      busy-label="Queueing…"
      @confirm="confirmSubmit"
      @cancel="showSubmitConfirm = false"
    >
      <dl v-if="!busy" class="confirm-summary">
        <div><dt>Query</dt><dd class="mono">{{ queryPreview() }}</dd></div>
        <div><dt>Question</dt><dd>{{ fullQuestion() || 'Identify this sequence' }}</dd></div>
        <div><dt>Program</dt><dd>{{ modeLabel }}</dd></div>
        <div><dt>Search on</dt><dd>{{ backendLabels[searchBackend] }}</dd></div>
        <div><dt>Database</dt><dd>{{ databaseLabel }}</dd></div>
      </dl>
      <p v-else class="confirm-progress">
        <span class="spinner" aria-hidden="true" />
        Queueing your search — opening the live workflow page next.
      </p>
      <p v-if="searchBackend === 'ncbi' && !busy" class="hint">
        Your sequence will be sent to NCBI's public BLAST service.
      </p>
    </ConfirmDialog>

    <ConfirmDialog
      :open="showResetConfirm"
      title="Reset this form?"
      confirm-label="Reset form"
      danger
      @confirm="resetForm"
      @cancel="showResetConfirm = false"
    >
      <p>Every field goes back to its default. This cannot be undone.</p>
    </ConfirmDialog>
  </main>
</template>
