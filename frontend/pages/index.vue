<script setup lang="ts">
const { status } = useAuth()

const samples = [
  { label: 'Beta globin in nematodes', sequence: 'NP_000509', question: 'Is there a related gene in nematodes, and how confident can I be?' },
  { label: 'Insulin in C. elegans', sequence: 'NP_000198', question: 'Is there an insulin homolog in C. elegans?' },
  { label: '12-aa short query', sequence: 'PNLHGLFGRKTG', question: 'What is this short peptide?' },
]

function sampleLink(s: (typeof samples)[number]) {
  return `/new?sequence=${encodeURIComponent(s.sequence)}&question=${encodeURIComponent(s.question)}`
}
</script>

<template>
  <main class="page">
    <section class="hero">
      <div class="hero-grid">
        <div>
          <p class="kicker">BLAST workflows for occasional users</p>
          <h1>Ask once. Get a verified gene answer.</h1>
          <p class="lede">
            Paste an accession or sequence and ask in plain words. WhatsGene picks the BLAST program
            with fixed rules, runs the search in the background, and classifies every hit in code —
            so you read a verdict with the exact E-value, identity and coverage behind it.
          </p>
          <p class="cta-row">
            <template v-if="status === 'out'">
              <NuxtLink to="/login?next=/new" class="btn">Log in to start a search →</NuxtLink>
            </template>
            <template v-else>
              <NuxtLink to="/new" class="btn">Start a search →</NuxtLink>
              <NuxtLink to="/jobs" class="quiet-link">View your workflows →</NuxtLink>
            </template>
          </p>
          <div class="hero-samples">
            <p>Try a sample search</p>
            <div class="sample-row" style="margin-top: 0;">
              <NuxtLink v-for="s in samples" :key="s.label" :to="sampleLink(s)" class="sample-chip">{{ s.label }}</NuxtLink>
            </div>
          </div>
        </div>

        <aside class="preview-card" aria-label="Example result">
          <div class="preview-head">
            <span class="status-pill status-done">done</span>
            <span class="mono">NP_000509 · blastp / nr</span>
            <span class="preview-label">Example</span>
          </div>
          <div class="preview-body">
            <p class="preview-verdict">Confirmed — a beta-globin homolog in nematodes, backed by a strong reciprocal hit.</p>
            <dl class="preview-stats">
              <div><dt>E-value</dt><dd>3e-48</dd></div>
              <div><dt>Identity</dt><dd>68%</dd></div>
              <div><dt>Coverage</dt><dd>96%</dd></div>
            </dl>
            <ul class="preview-log">
              <li><span class="mono">STEP 1</span> Rules engine picked blastp — protein query, protein database.</li>
              <li><span class="mono">STEP 2</span> Top hit classified <strong>strong</strong> by fixed thresholds in code.</li>
              <li><span class="mono">STEP 3</span> Reciprocal check passed. Verdict stored with full parameters.</li>
            </ul>
          </div>
        </aside>
      </div>
    </section>

    <p class="section-label">How a run goes</p>
    <h2 style="margin-top: 0;">Three steps, no queue-watching</h2>
    <div class="tool-grid">
      <article class="step-card">
        <span class="step-num">1</span>
        <h3>You ask</h3>
        <p>Accession or raw sequence, a target organism, your question. Queue several searches and keep working — each one runs on its own.</p>
      </article>
      <article class="step-card">
        <span class="step-num">2</span>
        <h3>WhatsGene searches</h3>
        <p>The rules engine picks blastn, blastp, blastx, tblastn or tblastx and the matching database. Long queues finish in the background.</p>
      </article>
      <article class="step-card">
        <span class="step-num">3</span>
        <h3>Code verifies, you read</h3>
        <p>Hits are labelled strong, borderline or not significant by fixed thresholds. The top candidate must pass reciprocal, coverage and length checks.</p>
      </article>
    </div>

    <p class="section-label">What you get back</p>
    <h2 style="margin-top: 0;">A result you can defend</h2>
    <dl class="feature-list">
      <div><dt>Verdict</dt><dd>Confirmed or not confirmed, in plain words — with the top hit named.</dd></div>
      <div><dt>Evidence</dt><dd>E-value, % identity, % coverage and classification, quoted exactly as computed.</dd></div>
      <div><dt>Reproducibility</dt><dd>Program, database, E cutoff, word size and matrix — everything needed to rerun it.</dd></div>
      <div><dt>Follow-ups</dt><dd>Ask about the stored run. Answers quote stored values or say they cannot answer.</dd></div>
    </dl>

    <div class="notice">
      Short protein queries (30 aa or fewer) switch to the short-query profile automatically: E-value cutoff 200,000, word size 2, matrix PAM30. Every search stores the exact settings it ran with.
    </div>

    <h2>Status while you wait</h2>
    <p style="max-width: 70ch; color: var(--muted); line-height: 1.65;">
      Workflows move <strong style="color: var(--ink-2);">queued → running → done</strong> (or failed / cancelled).
      A notification pops up here the moment each one finishes. WhatsApp delivery is deferred until Meta verifies
      the business account, so this page is the way to submit, track and ask for now.
    </p>
  </main>
</template>
