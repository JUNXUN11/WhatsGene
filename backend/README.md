# WhatsGene — Backend (FastAPI)

FastAPI + SQLite + background worker. See `../docs/ARCHITECTURE.md`.

## Run

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in NCBI_EMAIL at minimum
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

Live NCBI submission is behind `app/blast_backend.py` (NCBIWebBackend) and
is not wired yet — the loop reports that clearly instead of faking results.
WhatsApp is the product entry point (`POST /webhooks/whatsapp`); `POST /jobs`
remains for dev/testing.
