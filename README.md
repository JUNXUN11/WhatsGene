# WhatsGene

**BLAST for people who don't use BLAST every day.**

WhatsGene removes the manual glue around BLAST: resolving sequences,
interpreting significance, comparing strategies, and recording every run
for reproducibility. Submit once on the website — WhatsGene queues a
background workflow, runs BLAST searches in parallel, shows live status,
and replies with context: why this program, the exact parameters, the top
hit, and how confident you can be.

Built with Muse Spark Open. For research and education only — not
medical advice.

## What it does

- **Parallel BLAST workflows.** One submission is a workflow: `auto`
  (fixed rules pick one program), `single` (you pick, validated in code),
  or `all` (every program that accepts your query type: protein →
  blastp + tblastn; DNA → blastn + blastx + tblastx). Queue several at
  once; each runs in the background with queued → running → done status.
- **Every run is recorded.** Program, database, exact parameters
  (E-value threshold, word size, matrix), date, and search ID per search,
  plus parsed hits and the agent step log with reasons.
- **Significance in code, never in the model.** Hits are labelled strong /
  borderline / not significant by fixed thresholds (never significant if
  E > 0.05; the working cut is stricter). Top candidates must pass
  reciprocal, coverage, length, and annotation checks.
- **Short queries just work.** A short protein query (e.g. the 12-aa Lab
  case `PNLHGLFGRKTG`) automatically gets the short-query profile:
  E-value cutoff 200,000, word size 2, PAM30 — shown next to the defaults
  (E=10, word 3, BLOSUM62) so the settings are never a mystery. CDS
  subranges work too: submit `NM_006744.4:84-689`.
- **Ask, grounded.** Follow-up questions on the website are answered only
  from stored results, quoting actual E-values, identity, and coverage —
  or saying plainly that the stored results cannot answer.

WhatsApp start/notify is built and inbound-proven, but outbound delivery
is currently gated by Meta business verification, so the website is the
entry point. After the website work is complete, WhatsApp is retried
first, with Telegram as the fallback notification channel.

## Run it

```bash
# Backend (terminal 1)
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set SEARCH_BACKEND + BLASTDB (local) or NCBI_EMAIL (remote)
uvicorn app.main:app --reload --port 8000

# Frontend (terminal 2)
cd frontend
npm install
npm run dev   # http://localhost:3000
```

Search backends are chosen **per workflow on the website** (server default / local / real NCBI; `SEARCH_BACKEND` in `backend/.env` sets the host default): `local` (default —
BLAST+ against a local database at `$BLASTDB`), `ncbi` (opt-in remote:
submit at most once per in-flight search, poll each RID no more than once
a minute), `fixture` (recorded data for tests and demos).

## Reviewer demo login

The homepage is public; search, workflows and Ask need the reviewer
account. Set `AUTH_USERNAME`/`AUTH_PASSWORD` in `backend/.env` (created on
first startup); on the live HTTPS server also set `COOKIE_SECURE=true`.
Log in at `/login` — protected pages bounce there on their own. The live
Ask answers (Muse credit) stay off until `MODEL_ASK_ENABLED=true`, and are
then capped by `ASK_DAILY_LIMIT`/`JOBS_DAILY_LIMIT` with every call logged.

## Tests

```bash
cd backend && .venv/bin/python -m unittest discover -s tests
cd frontend && npm run build
```

Offline eval suite on textbook/lab cases (beta globin, insulin, RBP4,
neuroglobin-vs-mosses, short-query profile, CDS subrange, HIV-1 exclusion, MSA/tree): **105 tests,
all passing**, no network required.

## Not building yet (roadmap)

PSI-BLAST iterations, PHI-BLAST, HMMER, Tajima's test, bootstrapping,
HIV-1 organism-exclusion with unexpected-taxa flags. MSA → tree
follows the course rules when provided. (Single-user reviewer auth and
guarded model Ask shipped 1 Nov, decision 007.)
