# WhatsGene — Agent Guide

WhatsGene is "BLAST for people who don't use BLAST every day." Wet-lab biologists who run BLAST a few times a year ask once on WhatsApp; WhatsGene runs the whole multi-step search itself — rules engine chooses program/database, NCBI BLAST runs in the background, deterministic code classifies and verifies hits, the agent loop tries the next candidate or retries with adjusted settings — and returns a verified plain-language answer with a link to a web results page (hits, classifications, evidence, step log, exact parameters). Core principle: **the model interprets and explains; code computes and classifies.** Prototype for the Meta Global AI Developer Hackathon; submission deadline 4 Nov 2026 MYT. Product source of truth is `docs/PRD.md` v0.3.

## Stack (from docs/PRD.md §8)

- **Frontend:** Nuxt (Vue 3, TypeScript) — results pages only, no submission form; unguessable job links, never show phone numbers
- **Backend:** Python + FastAPI; Biopython for NCBI E-utilities (Entrez), BLAST parsing, and (Tier 2) neighbor-joining trees
- **Jobs/storage:** background worker running the agent loop, state in SQLite — no separate queue service
- **Agent layer:** Muse Spark Open via Modal Shared Endpoint (OpenAI-compatible); endpoint URL and model name from environment variables. Display "Built with Muse Spark Open" in the README and web footer
- **Main interface:** WhatsApp Cloud API (chat starts jobs, receives milestone progress and follow-ups); backend needs a public HTTPS URL for the webhook
- **BLAST backend:** an interface with one implementation now (NCBI web); local BLAST+ is post-submission private mode only

## Planned folder structure

```
frontend/          Nuxt results pages (linked from WhatsApp)
backend/           FastAPI API, agent loop worker, rules engine,
                   verification, BLAST backend, WhatsApp client
  tests/fixtures/  recorded NCBI responses for the offline eval harness
docs/
  PRD.md           product requirements — source of truth
  blast-rules.md   BLAST domain rules — source of truth for science
  ARCHITECTURE.md  system design and data flow
  ROADMAP.md       tier-gated phases and done-when conditions
  decisions/       NNN-title.md decision records
CHANGELOG.md       appended at the end of each roadmap phase
AGENTS.md          this file
```

## Rules

- `docs/PRD.md` and `docs/blast-rules.md` are the source of truth. Never change them without asking the owner first.
- Model interprets and explains; code computes and classifies. The model turns free text into structured intent; the rules engine maps intent + input type to program/database. The model may propose a deviation only with a stated reason — every deviation is logged and shown to the user. Significance classification and hit verification are always in code.
- Significance thresholds (E-value, identity, coverage) live in code/config only, traceable to `docs/blast-rules.md`. Never put them in model prompts.
- **Tier gating:** Tier 2 does not start until Tier 1 works end to end. Tier 3 only if Tier 2 is done by 3 Nov. Anything not working by 3 Nov is cut, not rushed.
- Every agent-loop decision is logged with its reason; every job has a configurable run budget (max searches, max time) — on exhaustion, stop and report what was and was not found.
- Follow-up answers come only from stored job results and `docs/blast-rules.md`, quoting actual E-value/identity/coverage. If stored results cannot answer, say so.
- Research memory is our own SQLite implementation keyed by WhatsApp number. Never describe it as a built-in model feature. Honour "forget my history" deletes.
- Do not invent MSA/phylogeny rules. They come from course decks 06 and 07 when the owner provides them. Verify PSI-BLAST support in NCBI's web API before building escalation; if unsupported, record it in PRD Open questions.
- Ask before adding any dependency or service not named in the PRD.
- Follow NCBI etiquette (polite polling, tool + contact email); show program/database/parameters on every results page. Warn users that sequences go to NCBI's public BLAST service and state what job history is kept, for how long, and how to delete it.

## Documentation rules

- Non-obvious choice → add `docs/decisions/NNN-title.md` (next free number, short: context, decision, consequence).
- Component or data-flow change → update `docs/ARCHITECTURE.md` in the same commit.
- End of each roadmap phase → append an entry to `CHANGELOG.md` and tick the phase in `docs/ROADMAP.md`.
- **After each task:** append a short entry to `CHANGELOG.md` describing what Muse did in that task, and tick the phase in `docs/ROADMAP.md` if that task completes its "done when". Do this before reporting the task as done.

## Run and test

```bash
# Backend (terminal 1)
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # NCBI_EMAIL + Muse Modal endpoint/model + WhatsApp creds
uvicorn app.main:app --reload --port 8000   # http://localhost:8000/health · /docs

# Frontend (terminal 2)
cd frontend
npm install
npm run dev   # http://localhost:3000 (results pages; backend must be running)

# Tests
# backend:  cd backend && .venv/bin/python -m app.tests.test_classify
# evals:    offline fixture suite by default; live NCBI suite optional only
# frontend: cd frontend && npm run build
```
