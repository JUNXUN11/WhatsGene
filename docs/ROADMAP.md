# WhatsGene — Roadmap

> Deadline: **4 Nov 2026 MYT**. Scope is `docs/PRD.md` (v0.3); science is `docs/blast-rules.md`. **Tier 2 does not start until Tier 1 works end to end.** Tick a phase here and append to `CHANGELOG.md` when its "done when" is met (see `AGENTS.md`). Anything not working by 3 Nov is cut, not rushed.

## Tier 1 — Core (must ship)

- [ ] **29 Oct — Docs + WhatsApp setup.** Approve PRD v0.3, `AGENTS.md`, `docs/blast-rules.md`, `docs/ARCHITECTURE.md`, this roadmap; get WhatsApp Cloud API access (Meta app, test number, webhook HTTPS URL) and verify current template-message rules for replies inside/outside the 24-hour window.
  - *Done when:* all docs are approved and a test message round-trips on the WhatsApp test number.
  - *Progress (29 Oct):* docs done — PRD rewritten to v0.3 and `ARCHITECTURE.md`, this roadmap, `AGENTS.md` and `docs/blast-rules.md` aligned to it. Remaining: WhatsApp API access, test-number round-trip, template-rule verification.

- [x] **30 Oct — Science core + eval harness.** Sequence/accession validation, E-utilities fetch, rules engine (intent + input type → program/database), hit classification and verification module (reciprocal best hit, coverage from coordinates, length, annotation) — all deterministic, traceable to `docs/blast-rules.md`. Eval harness on recorded fixtures for NP_000509 vs nematodes, NP_000198 vs *C. elegans*, RBP4 vs CG8.
  - *Done when:* the offline eval suite passes on program choice, false-positive rejection and true-hit confirmation (behaviour, not exact hit names).
  - *Progress (29 Oct, ticked on done-when):* offline eval suite passes (15 tests: globin tblastn choice + true-hit confirmation, insulin blastp + borderline, RBP4 weak-hit rejection). Remaining for live use: E-utilities fetch behind the BLAST backend interface is not wired yet.

- [ ] **31 Oct — Agent loop + WhatsApp chat + results page (Tier 1 end to end).** Agent loop with configurable budget, step log with reasons, logged deviations, next-candidate and adjusted-retry recovery; WhatsApp as main interface (sequence/accession starts a job, one running job per chat with cancel offer, milestone progress, grounded follow-ups from stored results only); results page with hits, classifications, evidence, step log and exact parameters — no submission form, unguessable links, no phone numbers. Web submit form from the boilerplate is removed or retired in this phase.
  - *Done when:* the beta globin workflow runs end to end on WhatsApp — submit, milestone updates, reciprocal confirmation, summary with results link — and one follow-up question is answered quoting stored E-value/identity/coverage.
  - *Progress (29 Oct):* done offline — agent loop with budget/step log/recovery, WhatsApp chat routing (start, one-per-chat + cancel, grounded follow-ups, forget-history), form-free results pages with step log. Remaining: live NCBI submission and live WhatsApp/Modal sends, then the on-WhatsApp end-to-end run this phase is judged on.

## Tier 2 — Muse showcase (in order; only after Tier 1 above is ticked)

- [ ] **1 Nov — Long-horizon workflow.** First verify PSI-BLAST support in NCBI's web API (if unsupported, record it under PRD Open questions and keep Tier 1 behaviour). Then: escalate on weak hits within the same budget/logging rules, collect confirmed homologs, run MSA (EBI Clustal Omega or MUSCLE via REST) and a Biopython neighbor-joining tree. Do not invent MSA/phylogeny rules; they come from course decks 06 and 07 when provided.
  - *Done when:* the beta globin run continues from confirmation into an MSA and tree on the results page, with every escalation decision in the step log.

- [ ] **2 Nov — Research memory.** Job history keyed by WhatsApp number in our own database (never described as a built-in model feature); link a new result to earlier relevant ones; honour "forget my history" by deleting that user's history. Add the extended data notice (what is kept, for how long, how to delete).
  - *Done when:* a second job in the same chat visibly links to the earlier job, and a forget request deletes the history and confirms it.

## Tier 3 — Stretch (only if Tier 2 is ticked before this date)

- [ ] **3 Nov — Feature freeze + demo.** No new features except Tier 3 (voice-note questions only, never sequences; screenshot → explanation) and only if Tier 2 finished in time. Record the demo video (beta globin WhatsApp run, agent steps, reciprocal confirmation, grounded follow-up; Tier 2 continuation and memory moment if shipped; time-lapse/cut for any 20+ minute run), run a labelled pre-run backup job, fix only demo-blocking bugs.
  - *Done when:* demo video is recorded and the backup job's results page and WhatsApp messages are verified working.

## Submission

- [ ] **4 Nov — README + submit.** README with setup via env vars, "Built with Muse Spark Open", and the eval harness score; repo cleanup; public repo + live link + video submitted before the MYT deadline.
  - *Done when:* repo, live app and video all open in a private browser window with no login, and the submission is sent.

## After submission (PRD §9)

- [ ] **Private self-hosted mode:** local BLAST+ backend implementation and a self-hosted model; WhatsApp carries summaries only.
  - *Done when:* a job runs end to end with no NCBI web or hosted-model calls.
- [ ] **Beta testing with real users** (occasional BLAST users and students).
  - *Done when:* at least five external users complete a real job end to end and feedback is logged as issues.
- [ ] **User accounts and teams.**
  - *Done when:* a user can sign in and share a job history with a team without using a WhatsApp number as the key.
