<template>
  <main class="page">
    <h1>BLAST for people who don't use BLAST every day</h1>
    <p class="lede">
      Ask once on WhatsApp. WhatsGene runs the whole search itself — it picks the BLAST
      program with fixed rules, submits and polls NCBI in the background, classifies and
      reciprocal-checks the hits in code, and replies with a verified answer and a link
      to the full results here.
    </p>

    <div class="card">
      <h2 style="margin-top: 0;">Start on WhatsApp</h2>
      <ol style="margin: 0; padding-left: 20px;">
        <li>Message the WhatsGene WhatsApp number with a sequence or accession and your question — for example: <em>NP_000509 — is there a related gene in nematodes?</em></li>
        <li>Keep working. You will get brief progress messages at major milestones, not a page to refresh.</li>
        <li>When it finishes, WhatsApp sends the verified summary and a link to your results page.</li>
        <li>Ask follow-ups in the same chat — answers quote the stored E-value, identity and coverage from your job.</li>
      </ol>
      <p class="hint">This website has no submission form by design: jobs start in WhatsApp chat, and these pages only show results.</p>
    </div>

    <div class="notice">
      Your sequence is sent to NCBI's public BLAST service. Job history is stored so
      follow-up questions can be answered; message “forget my history” on WhatsApp at any
      time to delete it.
    </div>

    <h2>How verification works</h2>
    <p>
      The model interprets your question; code computes and classifies. Hits are labelled
      strong, borderline, or not significant by fixed thresholds, the top candidate must
      pass a reciprocal search plus coverage, length and annotation checks, and every
      agent decision is logged with its reason on the results page — with the exact
      program, database and parameters, so you can reproduce the search at NCBI.
    </p>

    <h2>Example</h2>
    <p>
      “I have human beta globin (NP_000509). Is there a related gene in nematodes, and how
      confident can I be?” WhatsGene searches the protein against nematode EST sequences,
      verifies the best candidate reciprocally, and tells you how confident you can be —
      with the evidence, not just a hit list.
    </p>
  </main>
</template>
