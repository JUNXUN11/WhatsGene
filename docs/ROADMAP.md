# WhatsGene — Roadmap

> Deadline: **4 Nov 2026 MYT**. Scope is [PRD.md](PRD.md) (v0.3); science is [blast-rules.md](blast-rules.md). **Tier 2 does not start until Tier 1 works end to end.** A phase is ticked only when its "done when" is met. Anything not working by 3 Nov is cut, not rushed.
>
> Each phase shows the plan as signed off on 29 Oct, then what was delivered. Where delivery differs from the plan, the [PRD change table](PRD.md#changes-after-sign-off) says what changed.

## Tier 1 — Core (must ship)

- [x] **29 Oct — Docs + WhatsApp setup.** Approve the PRD v0.3, `blast-rules.md`, `ARCHITECTURE.md` and this roadmap. Get WhatsApp Cloud API access (Meta app, test number, webhook HTTPS URL) and verify the template-message rules.
  - *Done when:* all docs are approved and a test message round-trips on the WhatsApp test number.
  - *Delivered:* all docs signed off. WhatsApp inbound proven live; outbound replies blocked by Meta business verification.

- [x] **30 Oct — Science core + eval harness.** Sequence/accession validation, E-utilities fetch, rules engine, hit classification, verification module (reciprocal best hit, coverage, length, annotation). All deterministic, traceable to `blast-rules.md`. Eval harness on recorded fixtures for NP_000509 vs nematodes, NP_000198 vs *C. elegans*, RBP4 vs CG8.
  - *Done when:* the offline eval suite passes on program choice, false-positive rejection and true-hit confirmation.
  - *Delivered:* as planned. Local BLAST+ became the default backend.

- [x] **31 Oct — Agent loop + interface + results page (Tier 1 end to end).** Agent loop with budget, step log with reasons, logged deviations, next-candidate and retry recovery. Grounded follow-ups from stored results only. Results page with hits, classifications, evidence, step log and exact parameters.
  - *Done when:* the beta globin workflow runs end to end (submit, status updates, reciprocal confirmation, summary with results link) and one follow-up is answered from stored E-value, identity and coverage.
  - *Delivered:* end to end on the website instead of WhatsApp. Many workflows run in parallel; the Lab 04 short-query profile is applied automatically.

## Tier 2 — Muse showcase (in order; only after Tier 1)

- [x] **1 Nov — Long-horizon workflow.** Verify PSI-BLAST support. Escalate on weak hits within the same budget. Collect confirmed homologs, run an MSA and a neighbor-joining tree.
  - *Done when:* the beta globin run continues from confirmation into an MSA and tree on the results page, with every decision in the step log.
  - *Delivered:* MAFFT alignment and NJ tree (Poisson, complete deletion) from the results page. PSI-BLAST not built; kept on the roadmap. Also delivered: per-workflow Local vs real NCBI, login and guarded Muse Ask.

- [x] **2 Nov — Research memory.** Job history keyed by WhatsApp number; link new results to earlier ones; honour "forget my history".
  - *Done when:* a second job visibly links to an earlier job, and a forget request deletes the history.
  - *Delivered differently:* WhatsGene became a local tool on the owner's machine. History is per account and stays in the owner's SQLite file; users delete workflows in the app. Settings page with presets, custom cut-offs and the Muse key.

## Tier 3 — Stretch (only if Tier 2 is done before this date)

- [ ] **3 Nov — Feature freeze + demo.** Tier 3 only if Tier 2 finished in time: voice-note questions, screenshot explanation. Record the demo video and a pre-run backup job.
  - *Done when:* the demo video is recorded and the backup job's results page is verified.
  - *Delivered:* Tier 3 was cut. The day went to making the local tool usable by a non-engineer: six local NCBI databases, a named database per workflow, the file-drop library, custom databases and MCP tools, the one-address `./start`, the setup wizard, landing vs app builds, and no login on a one-person machine.

## Submission

- [x] **4 Nov — README + submit.** README with setup steps, eval harness passing, repo cleanup, public repo and video submitted before the deadline.
  - *Done when:* the repo and video open in a private browser window.
  - *Delivered:* README with a one-line install, 205 offline tests passing, owner-created accounts. No hosted live link, because WhatsGene is a local tool: the reviewer runs the tool on their own machine.

## After submission (PRD §9)

- [x] **Private self-hosted mode:** local BLAST+ and no WhatsGene server. *Delivered early*. A self-hosted model works through any OpenAI-compatible endpoint.
- [ ] **Beta testing with real users** (occasional BLAST users and students).
  - *Done when:* at least five external users complete a real job end to end and feedback is logged as issues.
- [ ] **User accounts and teams.** Accounts *delivered early*. Teams that share workflows are still open.
- [ ] **Science backlog:** PSI-BLAST escalation, bootstrapped trees, translated programs (`tblastn`, `blastx`) on local databases.
