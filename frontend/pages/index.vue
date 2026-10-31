<script setup lang="ts">
const { createJob } = useApi()
const router = useRouter()

const sequence = ref('')
const question = ref('')
const mode = ref<'auto' | 'single' | 'all'>('auto')
const program = ref('blastp')
const whatsapp = ref('')
const busy = ref(false)
const error = ref('')

const samples = [
  { label: 'Beta globin in nematodes', sequence: 'NP_000509', question: 'Is there a related gene in nematodes, and how confident can I be?' },
  { label: 'Lab 04 short query (12 aa)', sequence: 'PNLHGLFGRKTG', question: 'What E-value cutoff, word size and matrix were used, and how do they compare to the defaults?' },
  { label: 'Insulin in C. elegans', sequence: 'NP_000198', question: 'Is there an insulin homolog in C. elegans?' },
]

function useSample(s: (typeof samples)[number]) {
  sequence.value = s.sequence
  question.value = s.question
  error.value = ''
}

async function submit() {
  error.value = ''
  if (!sequence.value.trim()) {
    error.value = 'Paste a sequence, FASTA, or an accession first.'
    return
  }
  busy.value = true
  try {
    const job = await createJob(sequence.value.trim(), question.value.trim(), {
      workflow_mode: mode.value,
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
  <main class="page">
    <p style="font-size: 13px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--accent); font-weight: 700; margin: 0 0 8px;">WhatsGene — BLAST workflows</p>
    <h1>Run BLAST in parallel. Read a verified answer, not a hit list.</h1>
    <p class="lede">
      For people who don't use BLAST every day. Paste a sequence or accession below:
      WhatsGene queues a background workflow, picks the BLAST program with fixed rules
      (or runs every program that fits your query), searches in parallel, classifies and
      reciprocal-checks hits in code, and replies with the context — why this program,
      the exact E-value cutoff, word size and matrix, the top hit, and how confident
      you can be. Queue five searches in a minute; watch each one's status here.
    </p>
    <p style="font-size: 14px; color: var(--muted); margin: 0 0 8px;">
      Status you will see: <strong>queued → running → done</strong> (or failed / cancelled) ·
      every search stores its parameters and hits · ask follow-ups in the Ask box — answers quote stored values only.
    </p>

    <form class="card" @submit.prevent="submit">
      <label for="seq">Sequence, FASTA, or accession</label>
      <textarea id="seq" v-model="sequence" placeholder="NP_000509 — or paste FASTA / a raw sequence such as PNLHGLFGRKTG" />
      <div class="sample-row">
        <button v-for="s in samples" :key="s.label" type="button" @click="useSample(s)">{{ s.label }}</button>
      </div>

      <label for="q">Your question</label>
      <input id="q" v-model="question" type="text" placeholder="Is there a related gene in nematodes?">

      <label for="mode">Workflow</label>
      <select id="mode" v-model="mode" class="select">
        <option value="auto">Auto — rules engine picks the best program</option>
        <option value="all">Run all — every program that accepts this query type</option>
        <option value="single">Single — I choose the program</option>
      </select>
      <div v-if="mode === 'single'" style="margin-top: 10px;">
        <label for="prog">Program</label>
        <select id="prog" v-model="program" class="select">
          <option value="blastn">blastn (DNA → DNA)</option>
          <option value="blastp">blastp (protein → protein)</option>
          <option value="blastx">blastx (DNA → protein)</option>
          <option value="tblastn">tblastn (protein → DNA)</option>
          <option value="tblastx">tblastx (DNA → DNA, translated)</option>
        </select>
        <p class="hint">Incompatible program/query pairs are rejected with the applicable list — nothing is submitted.</p>
      </div>
      <p v-if="mode === 'all'" class="hint">Protein queries run blastp + tblastn; DNA queries run blastn + blastx + tblastx. Each stores its own parameters and hits for comparison.</p>

      <label for="wa">WhatsApp number for the done notification (optional)</label>
      <input id="wa" v-model="whatsapp" type="text" placeholder="e.g. 60123456789 — leave blank to just watch this page">
      <p class="hint">Stored server-side only, never shown on results pages. WhatsApp delivery is currently deferred (Meta business verification), so watch the workflows page for status today.</p>

      <button class="btn" type="submit" :disabled="busy">{{ busy ? 'Queueing…' : 'Queue workflow' }}</button>
      <p v-if="error" class="error">{{ error }}</p>
    </form>

    <div class="notice">
      Short protein queries (30 aa or fewer, e.g. the 12-aa Lab 04 query PNLHGLFGRKTG) use the
      short-query profile automatically: E-value cutoff 200,000, word size 2, matrix PAM30 —
      versus the BLASTP defaults E=10, word size 3, BLOSUM62. The exact settings are stored on
      every search and shown on the results page.
    </div>

    <h2>How it runs</h2>
    <p>
      Submissions queue instantly and run in the background — queue several in a row and keep
      working. Code validates and classifies; the model only interprets your question and words
      the summary. Hits are labelled strong, borderline, or not significant by fixed thresholds,
      the top candidate must pass reciprocal, coverage, length and annotation checks, and every
      decision is logged with its reason.
    </p>

    <h2>WhatsApp — coming back later</h2>
    <p>
      WhatsApp start-and-notify is built and its inbound path is proven, but Meta currently
      blocks our outbound replies until the business account is verified. So the website is
      the way in for now: submit, track, and ask here. When the website work is complete we
      retry WhatsApp; if it still cannot deliver, Telegram becomes the notification fallback.
      Nothing about your searches changes either way.
    </p>

    <h2>About this service</h2>
    <p style="font-size: 14px; color: var(--muted);">
      WhatsGene is a research and education tool run by Too Jun Xun (Malaysia) — not medical
      advice. Contact: junxun288@gmail.com. Your submitted sequence, question, search
      parameters and results are stored so your workflows and follow-up answers can be shown;
      local searches run on our server, and only remote (NCBI) searches send a sequence to
      NCBI's public BLAST service. Full policy: ask for the privacy link on the results page footer.
    </p>
  </main>
</template>

<style scoped>
.select {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 10px 12px;
  font: inherit;
  font-size: 15px;
  background: #fff;
  color: var(--ink);
}
</style>
