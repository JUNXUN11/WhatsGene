# WhatsGene — Backend (FastAPI)

FastAPI + SQLite + background worker. See `../docs/ARCHITECTURE.md`.

## Run

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set BLASTDB at minimum (or SEARCH_BACKEND=ncbi + NCBI_EMAIL)
uvicorn app.main:app --reload --port 8000
```

- Health: http://localhost:8000/health
- API docs: http://localhost:8000/docs
- Worker (separate terminal, takes over NCBI lifecycle on 30–31 Oct): `python -m app.worker`

## Test

```bash
source .venv/bin/activate
python -m app.tests.test_classify          # classification thresholds
python -m unittest discover -s tests -v    # offline eval harness + loop/chat (fixtures, no network)
```

Search backends live in `app/search_backend.py`, selected by `SEARCH_BACKEND`
in `.env`: `local` (default — BLAST+ `blastp`/`blastn` against a preformatted
swissprot copy at `$BLASTDB`), `ncbi` (opt-in remote: tool+email, max 1
in-flight RID, polls ≥ 60s apart, aborts after 30 min), `fixture` (recorded
JSON from `tests/fixtures`, for tests and demo). `cp .env.example .env` and set
`BLASTDB` (local) or `NCBI_EMAIL` + `SEARCH_BACKEND=ncbi` (remote).
Jobs start on the website (`POST /jobs`, queues a workflow and returns at once). The background worker runs many workflows in parallel (`python -m app.worker`, or the in-process drainer under uvicorn), each with live status and a rich context reply. Ask about a stored workflow via `POST /jobs/{id}/ask`. WhatsApp webhook/notify code is retained but deferred (outbound gated by Meta business verification); Telegram fallback comes only after the website is complete.
