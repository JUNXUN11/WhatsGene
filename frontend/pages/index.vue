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
          <h1>BLAST without the learning curve.</h1>
          <p class="lede">
            Paste a sequence or accession and ask in plain words. WhatsGene picks the BLAST program,
            runs the search on your own machine, and verifies every hit in code. You get a verdict
            with the exact E-value, identity and coverage behind it — stored in your history, ready to defend.
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
    <h2 style="margin-top: 0;">No queues, no lost results, no twenty settings</h2>
    <dl class="feature-list">
      <div><dt>Local and fast</dt><dd>Search your own database in seconds. Use the real NCBI service per workflow when you need it.</dd></div>
      <div><dt>Verified verdicts</dt><dd>Every hit is classified by fixed rules in code, and the top candidate must pass reciprocal, coverage and length checks.</dd></div>
      <div><dt>History, kept</dt><dd>Every workflow stays stored with its parameters, hits and step log. Queue several at once; nothing is lost.</dd></div>
      <div><dt>Open and extensible</dt><dd>Open source, local by default, with MCP tools so models can sort files, build databases and run searches.</dd></div>
    </dl>

    <p class="section-label">How a run goes</p>
    <h2 style="margin-top: 0;">Three steps</h2>
    <div class="tool-grid">
      <article class="step-card">
        <span class="step-num">1</span>
        <h3>You ask</h3>
        <p>Accession or sequence, plus your question in plain words.</p>
      </article>
      <article class="step-card">
        <span class="step-num">2</span>
        <h3>WhatsGene searches</h3>
        <p>The rules engine picks the program and database, then runs the search in the background.</p>
      </article>
      <article class="step-card">
        <span class="step-num">3</span>
        <h3>You read the verdict</h3>
        <p>Confirmed or not confirmed, with exact numbers and a step log you can cite.</p>
      </article>
    </div>

    <p class="section-label">Run it yourself</p>
    <h2 style="margin-top: 0;">Download WhatsGene</h2>
    <p style="max-width: 70ch; color: var(--muted); line-height: 1.65; margin-top: 0;">
      WhatsGene runs on your own Mac or Linux machine — your sequences never leave it.
      Paste this one line in a terminal. It downloads the tool, starts it, and opens your browser.
      Inside, press <strong style="color: var(--ink-2);">Run setup now</strong> (Settings → Local BLAST setup)
      and the wizard downloads and builds the database for you.
    </p>
    <pre class="install-line mono">curl -fsSL https://raw.githubusercontent.com/JUNXUN11/WhatsGene/main/install.sh | bash</pre>
    <p class="hint">Needs Git, Python 3.12+, Node 20+ and NCBI BLAST+ (the installer checks and tells you what is missing). Prefer manual steps? The README walks through them.</p>
  </main>
</template>

<style scoped>
.install-line {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 14px 16px;
  font-size: 13.5px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-width: 70ch;
}
</style>
