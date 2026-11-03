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

const siteMode = useRuntimeConfig().public.siteMode
const installCmd = 'curl -fsSL https://raw.githubusercontent.com/JUNXUN11/WhatsGene/main/install.sh | bash'
const copied = ref(false)

async function copyInstall() {
  try {
    await navigator.clipboard.writeText(installCmd)
  } catch {
    const ta = document.createElement('textarea')
    ta.value = installCmd
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    ta.remove()
  }
  copied.value = true
  window.setTimeout(() => { copied.value = false }, 2000)
}
</script>

<template>
  <main class="page">
    <section class="hero">
      <p class="kicker">Open-source BLAST workflows for occasional users</p>
      <h1>Your own local BLAST</h1>
      <div class="install-box" role="group" aria-label="Install command">
        <code class="mono">{{ installCmd }}</code>
        <button type="button" class="btn-copy" @click="copyInstall">{{ copied ? 'Copied ✓' : 'Copy' }}</button>
      </div>
      <p class="hint">Needs Git, Python 3.12+, Node 20+ and NCBI BLAST+. Inside the app: Settings → Local BLAST setup → Run setup now.</p>
      <div class="hero-grid">
        <div>
          <p class="lede">
            Paste a sequence or accession and ask in plain words. WhatsGene picks the BLAST program,
            runs the search on your own machine, and verifies every hit in code. You get a verdict
            with the exact E-value, identity and coverage behind it — stored in your history, ready to defend.
          </p>
          <div v-if="siteMode !== 'landing'" class="hero-samples">
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

  </main>
</template>

<style scoped>
/* Full-width hero: title and command span the page, description and
   example sit side by side below. */
.hero h1 {
  max-width: none;
}
.install-box {
  display: flex;
  align-items: stretch;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 10px;
  margin: 18px 0 8px;
  overflow: hidden;
}
.install-box code {
  flex: 1;
  align-self: center;
  padding: 12px 14px;
  font-size: 12.5px;
  overflow-wrap: anywhere;
}
.btn-copy {
  border: 0;
  border-left: 1px solid var(--line);
  background: var(--accent);
  color: var(--accent-ink);
  padding: 0 20px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}
.btn-copy:hover {
  background: var(--accent-strong);
}
</style>
