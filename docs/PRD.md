# WhatsGene — Product Requirements Document

**Status:** v0.3 · **Date:** 29 Oct 2026 · **Owner:** Too Jun Xun
**Context:** Meta Global AI Developer Hackathon (Cerebral Valley). Built with Meta Muse models.
**Submission deadline:** 4 Nov 2026, Malaysia time (MYT, UTC+8)

> **Pitch:** BLAST for people who don't use BLAST every day.

> **Baseline document.** This is the requirements baseline that was signed off on 29 Oct 2026. Its body is not rewritten. Changes made during the build are listed in [Changes after sign-off](#changes-after-sign-off) at the end of this file.

## 1. Positioning and problem

WhatsGene is built on **delegate-and-verify**: the user asks once; WhatsGene runs the whole multi-step search itself, checks hits with fixed rules, and returns a verified answer. The user does not drive each step.

Finding whether a gene or protein has relatives in other organisms is a routine molecular-biology task and BLAST is the standard tool, but occasional users struggle to choose among five BLAST programs and many databases, to judge E-values, bit scores, identity and coverage, to verify hits with reciprocal searches and length/annotation checks, and to wait minutes for web BLAST to finish. WhatsGene removes that burden.

**Why not just use a chatbot?** A chatbot advises: it suggests a program, the user runs the search, pastes results back, and repeats. The user still does the work and the chatbot never executes or verifies anything. WhatsGene does the work — it submits, polls, parses, classifies and reciprocal-checks the search itself — and verifies the answer with deterministic rules before replying.

Core example: *"I have human beta globin (NP_000509). Is there a related gene in nematodes, and how confident can I be?"* Domain rules live in `docs/blast-rules.md` (SECB2103 BLAST deck; Pevsner, *Bioinformatics & Functional Genomics* 3e, ch. 4).

## 2. Users

- **Primary: occasional BLAST users** — e.g. wet-lab biologists who run BLAST a few times a year and are effectively first-timers each time. They know the biology and their question; they do not know which search answers it or how to judge the output.
- **Secondary: students learning the BLAST workflow**, who benefit from seeing each choice explained.
- **Not for:** experienced bioinformaticians with their own scripts.

## 3. Core architecture principle

**The model interprets and explains; code computes and classifies.** This is a non-functional requirement, not a preference.

- The model turns the user's free-text question into a structured intent: goal, target organism or group, anything unclear.
- The rules engine maps intent + detected input type to BLAST program and database, using `docs/blast-rules.md`.
- The model may propose a deviation from the rules engine's choice only with a stated reason; every deviation is logged and shown to the user.
- Significance classification and hit verification are always done in code. Thresholds live in code/config, traceable to `docs/blast-rules.md` — never in model prompts.

## 4. Tier 1 — Core (must ship)

Tier 2 does not start until Tier 1 works end to end.

### 4.1 Agent loop

The agent plans the workflow, runs each step, and chooses the next step from what it observed: classify hits → pick candidate → reciprocal check → drop and try the next candidate if not confirmed → retry with adjusted settings if too few hits. The reason for every decision is logged and shown on the results page.

- **Run budget per job:** maximum number of searches and maximum total time, both configurable. When the budget runs out, stop and report what was found and what was not.
- Stopping conditions and recovery from failed or empty searches are defined behaviour, not improvised by the model.

### 4.2 Science core (deterministic code)

Rules engine plus a verification module: reciprocal best hit, query coverage from hit coordinates, length mismatch, annotation check. Every rule is traceable to `docs/blast-rules.md`. Also included: sequence/accession input validation (DNA vs protein detection, malformed input rejected with a specific error), fetching sequences by accession via NCBI E-utilities, and asynchronous NCBI BLAST jobs (submit → poll → parse).

### 4.3 Eval harness (textbook cases)

Built from textbook cases: beta globin NP_000509 vs nematodes; insulin NP_000198 vs *C. elegans*; RBP4 vs CG8 false positives. It measures program choice, rejection of false positives, and confirmation of true hits.

- Default suite runs offline on recorded NCBI responses (fixtures), so it is fast and repeatable. A separate, optional live suite runs against NCBI.
- Tests check behaviour, not exact hit names; NCBI databases have changed since the textbook.

### 4.4 WhatsApp chat (main interface)

- A message containing a sequence or accession starts a new job. Other messages are follow-up questions, by default about the latest job; the user may refer to an earlier job.
- One running job per chat. If a new sequence arrives during a run, reply that a job is running and offer to cancel it.
- Send brief progress messages at major milestones only, not every step.
- Follow-up answers come only from stored job results and the rules file, quoting actual values (E-value, identity, coverage). If the stored results cannot answer, say so.

### 4.5 Results page (web, linked from chat)

Shows hits, classifications, evidence, the agent's step log with reasons, and exact parameters for reproducibility. **No submission form.** Links use unguessable IDs; pages never show phone numbers.

## 5. Tier 2 — Muse showcase (should ship, in this order)

### 5.1 Long-horizon workflow

Escalate to PSI-BLAST when hits are too weak (verify that NCBI's web API supports this; if not, see Open questions). After confirmation, collect confirmed homologs, run a multiple sequence alignment (EBI Clustal Omega or MUSCLE via REST), and build a neighbor-joining tree (Biopython). Same budget, logging and decision rules as Tier 1. Detailed MSA/phylogeny rules will come from course decks 06 and 07, to be provided later; do not invent those rules now.

### 5.2 Research memory across chats

Store each user's job history keyed by their WhatsApp number (no accounts). When relevant, link a new result to earlier ones. This is our own implementation in our database; never describe it as a built-in model feature. Users can ask WhatsGene to forget their history.

## 6. Tier 3 — Stretch (only if Tier 2 is done by 3 Nov)

- Voice-note follow-up questions (questions only, never sequences).
- Screenshot of an existing BLAST result → explanation.

## 7. How WhatsGene showcases Muse

| Feature | Muse strength demonstrated |
|---|---|
| Multi-step Find-a-Gene run with decisions, retries and escalation (Tier 1 loop + Tier 2 §5.1) | Long-horizon agent execution |
| Research memory (Tier 2 §5.2), implemented by us on top of the model | Memory across conversations |
| The product as a whole: an expert bioinformatics workflow made usable by non-experts | Specialised professional workflows |

## 8. Tech and model

- **Stack:** Nuxt frontend, FastAPI backend, SQLite with a background worker, Biopython for NCBI access and parsing.
- **Model:** Muse Spark Open via Modal Shared Endpoint (OpenAI-compatible). Endpoint URL and model name are configurable via environment variables. Display "Built with Muse Spark Open" in the README and the web footer (license requirement).
- **BLAST backend as an interface:** one implementation now (NCBI web); local BLAST+ is the roadmap private mode (see §9).
- **Hosting:** any service giving the backend a public HTTPS URL (required for the WhatsApp webhook). Configuration through environment variables, with documented setup.
- **Transparency:** every summary and results page shows program, database and parameters so a user can reproduce the search.

## 9. Roadmap (after submission)

- Private self-hosted mode: local BLAST+ and a self-hosted model; WhatsApp carries summaries only.
- Beta testing with real users.
- User accounts and teams.

## 10. Success by submission (4 Nov 2026 MYT)

In priority order:

1. End-to-end WhatsApp demo of the beta globin workflow: agent steps, reciprocal confirmation, one grounded follow-up question.
2. If Tier 2 ships: the same run continuing into MSA and a tree, plus one moment showing memory of an earlier job.
3. Eval harness passing on the textbook cases, score reported in the README.
4. Public open-source repo with setup instructions and a license.

Anything not working by 3 Nov is cut, not rushed.

## 11. Data, etiquette and risks

- **Data notice:** tell users their sequences are sent to NCBI's public BLAST service (some may be unpublished). Extended for stored job history: the notice must state what is kept, for how long, and how to delete it, including the "forget my history" request in §5.2.
- **NCBI etiquette:** follow NCBI's current usage guidelines for polling frequency, request rates, and identifying the tool and contact email.
- **Risks:**
  - NCBI latency varies widely; the demo may need a pre-run backup job.
  - WhatsApp: user-initiated chats should keep replies inside the 24-hour window, but verify current template-message rules early.
  - Long runs (20+ minutes) need a time-lapse or cut in the demo video.
  - PSI-BLAST availability through NCBI's web API is unverified (see Open questions).
  - Database drift: textbook hit names may no longer appear; evals check behaviour (§4.3).

## 12. Related documents

- `docs/blast-rules.md` — domain rules (source of truth for science)
- `docs/ARCHITECTURE.md` — system design
- `docs/ROADMAP.md` — delivery phases

## Open questions

The following contradictions or gaps were found while writing v0.3. They are recorded here, not resolved silently. The status column was added after the build.

| # | Question | Status after the build |
|---|---|---|
| 1 | **Run budget defaults:** §4.1 requires configurable maximum searches and maximum total time per job, but no default values are specified. | Resolved in config: 6 searches and 1800 s per job (`MAX_SEARCHES_PER_JOB`, `MAX_JOB_SECONDS`). |
| 2 | **PSI-BLAST via NCBI web API:** §5.1 depends on it and §11 flags it as unverified. If unsupported, the escalation path (and the fallback) is undefined. | Not built. Kept on the roadmap. |
| 3 | **MSA service choice:** §5.1 allows EBI Clustal Omega *or* MUSCLE via REST; which one is the Tier 2 default is not decided. MSA/phylogeny rules await decks 06 and 07. | Resolved: MAFFT (local when installed, else EBI), neighbor-joining tree with Poisson distance and complete deletion. |
| 4 | **Job-history retention:** §11 requires the data notice to state what is kept and for how long, but no retention period or deletion mechanics beyond "forget my history" are specified. | Resolved: WhatsGene is a local tool, so data stays in the owner's own SQLite file until the user deletes the workflow. |
| 5 | **Memory relevance:** §5.2 links a new result to earlier ones "when relevant", but the relevance criterion is not defined. | Moot. Memory by WhatsApp number was replaced by per-account workflow history. |
| 6 | **Results-page access without WhatsApp:** §4.5 gives the web no submission form and §4.4 makes WhatsApp the main interface. How a user without WhatsApp (or outside the test-number allow-list during the hackathon) starts a job is not specified. | Resolved: the website has a submission form and is the main interface. |
| 7 | **Deviation authority:** §3 lets the model propose a deviation from the rules engine with a stated reason, logged and shown. Whether the deviation then applies automatically or needs user confirmation is not specified. | Resolved in config: a deviation is logged and shown, and applies only when `DEVIATION_AUTO_APPLY=true` (default false). |
| 8 | **Follow-up scope:** §4.4 defaults follow-ups to the latest job. How a reference to an earlier job is resolved when the description is ambiguous is not specified. | Resolved: Ask is per results page; on WhatsApp a `WG-…` ID selects the workflow. |

## Changes after sign-off

Each row is a change request against this baseline, approved by the owner during the build.

| PRD section | Baseline said | Changed to |
|---|---|---|
| §4.4, §4.5 | WhatsApp is the main interface; one job per chat; no web submission form | Website workflows first: web form, many workflows in parallel, live status; WhatsApp code kept but deferred |
| §5.1 | MSA service undecided | MAFFT plus NJ tree (Poisson, complete deletion) |
| §5.2 | Research memory keyed by WhatsApp number, no accounts | Accounts with private workflows per person; owner adds people |
| §6 | Tier 3: voice notes, screenshots | Cut, not rushed (§10 rule) |
| §8, §9 | NCBI web is the only backend; local BLAST+ after submission; public HTTPS host | Local tool on the owner's machine; local BLAST+ is the default; NCBI per workflow; one-address `./start` |
| §8 | Muse Spark Open via Modal | Any OpenAI-compatible Muse endpoint (Meta Model API, Modal, Baseten); the user pastes a key in Settings |
| §3 | Thresholds in code/config only | Defaults unchanged; an owner may set custom cut-offs, validated in code, never by a model |
| §11 | Sequences go to NCBI | Nothing leaves the machine in local mode; each remote path is opt-in and labelled |
| Not in baseline | — | Local database set, named database per workflow, file-drop library, custom databases, MCP tools, setup wizard, landing vs app build |
