# WhatsGene — Backend (FastAPI)

FastAPI + SQLite + an in-process worker. Design: [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).

The standard run is `./start` from the repo root, which serves the backend and the built site on `http://127.0.0.1:8000`. To run the backend alone:

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # BLASTDB defaults to ~/blastdb when unset
uvicorn app.main:app --reload --port 8000
```

- Health: http://localhost:8000/health
- API docs: http://localhost:8000/docs
- Standalone worker (optional): `python -m app.worker`
- MCP server over stdio: `python -m app.mcp_server`

Search backends live in `app/search_backend.py`, selected by `SEARCH_BACKEND` and per workflow:

| Backend | What |
|---|---|
| `local` (default) | BLAST+ `blastp` / `blastn` against databases in `$BLASTDB` |
| `ncbi` | NCBI E-utilities + BLAST URL API; needs `NCBI_EMAIL` |
| `fixture` | Recorded JSON from `tests/fixtures`, for tests |

## Test

```bash
.venv/bin/python -m unittest discover -s tests -v    # 205 offline tests, no network
.venv/bin/python -m app.tests.test_classify           # classification thresholds
```
