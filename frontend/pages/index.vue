<script setup lang="ts">
// Guests only (middleware redirects logged-in visitors to /new).
definePageMeta({ middleware: 'guest' })

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
          <p class="kicker">Open-source BLAST workflows for occasional users</p>
          <h1>Ask once. Get a verified gene answer.</h1>
          <p class="lede">
            Paste an accession or sequence and ask in plain words. WhatsGene picks the BLAST program
            with fixed rules, runs the search locally or on NCBI, and classifies every hit in code —
            so you read a verdict with the exact E-value, identity and coverage behind it.
            No parameters to learn first. No closed tab that loses your result.
          </p>
          <p class="cta-row">
            <NuxtLink to="/login?next=/new" class="btn">Log in to start a search →</NuxtLink>
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
            <span class="mono">P68871 · blastp / swissprot</span>
            <span class="preview-label">Example</span>
          </div>
          <div class="preview-body">
            <p class="preview-verdict">Confirmed — human beta globin (HBB), verified by a strong reciprocal best hit.</p>
            <dl class="preview-stats">
              <div><dt>E-value</dt><dd>6.6e-106</dd></div>
              <div><dt>Identity</dt><dd>100%</dd></div>
              <div><dt>Coverage</dt><dd>100%</dd></div>
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

    <p class="section-label">Why WhatsGene</p>
    <h2 style="margin-top: 0;">Built for the pain, not just the search</h2>
    <dl class="feature-list">
      <div><dt>Slow peak-time queues</dt><dd>Search your own local database in seconds. Switch to the real NCBI service per workflow when you need its full databases.</dd></div>
      <div><dt>No history</dt><dd>Every workflow is stored with its parameters, hits, step log and verdict. Close the tab — nothing is lost.</dd></div>
      <div><dt>Many windows, many searches</dt><dd>Queue several searches at once and keep working. Status and completion arrive on the same page.</dd></div>
      <div><dt>No 1 TB download</dt><dd>Build small databases you actually need: from your own FASTA files, or from one species in the built-in copy.</dd></div>
      <div><dt>Steep learning curve</dt><dd>One plain question replaces twenty BLAST settings. The rules engine chooses the program; Muse explains the setup and the result.</dd></div>
      <div><dt>Messy files</dt><dd>Drop any files into the inbox. WhatsGene reads and sorts them, and sorted sequences become searches or databases with one click.</dd></div>
    </dl>

    <p class="section-label">How a run goes</p>
    <h2 style="margin-top: 0;">Three steps, no queue-watching</h2>
    <div class="tool-grid">
      <article class="step-card">
        <span class="step-num">1</span>
        <h3>You ask</h3>
        <p>Accession or raw sequence, a target organism, your question — or a dropped file. Queue several searches and keep working; each one runs on its own.</p>
      </article>
      <article class="step-card">
        <span class="step-num">2</span>
        <h3>WhatsGene searches</h3>
        <p>The rules engine picks the BLAST program and database: your fast local copy by default, the real NCBI service when the workflow needs it.</p>
      </article>
      <article class="step-card">
        <span class="step-num">3</span>
        <h3>Code verifies, you read</h3>
        <p>Hits are labelled strong, borderline or not significant by fixed thresholds. The top candidate must pass reciprocal, coverage and length checks.</p>
      </article>
    </div>

    <p class="section-label">Local, open, extensible</p>
    <h2 style="margin-top: 0;">One researcher, one local tool</h2>
    <dl class="feature-list">
      <div><dt>Local by default</dt><dd>Databases and results live on your own machine. Remote services only ever see what you explicitly send them.</dd></div>
      <div><dt>Reproducible</dt><dd>Program, database, E cutoff, word size and matrix are stored and shown on every result — the same fields NCBI reports.</dd></div>
      <div><dt>Muse-guided</dt><dd>Paste a Muse key in Settings and Muse plans your database setup and explains workflow results in plain words.</dd></div>
      <div><dt>Agent-ready</dt><dd>The library and search functions are MCP tools, so any MCP-capable model can inventory files, build databases and run searches.</dd></div>
    </dl>

    <div class="notice">
      Short protein queries (30 aa or fewer) switch to the short-query profile automatically: E-value cutoff 200,000, word size 2, matrix PAM30. Every search stores the exact settings it ran with.
    </div>

    <h2>A result you can defend</h2>
    <p style="max-width: 70ch; color: var(--muted); line-height: 1.65;">
      Workflows move <strong style="color: var(--ink-2);">queued → running → done</strong> (or failed / cancelled)
      and stay in your history with their verdict: confirmed or not confirmed, the top hit named, and
      E-value, identity and coverage quoted exactly as computed. Ask follow-ups about any stored run —
      answers quote stored values or say they cannot answer.
    </p>
  </main>
</template>
