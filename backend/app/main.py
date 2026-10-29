"""WhatsGene FastAPI app — WhatsApp webhook, results API, health.

Main interface is WhatsApp chat (PRD §4.4); the web API serves results
pages only. POST /jobs remains as a dev/test entry point.

Run:
    uvicorn app.main:app --reload --port 8000
Docs: http://localhost:8000/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import chat, config, db
from .agent_loop import process_job
from .blast_backend import NCBIWebBackend


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="WhatsGene", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_BASE_URL, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class JobCreate(BaseModel):
    sequence: str = Field(description="FASTA text, raw sequence, or NCBI accession (e.g. NP_000509)")
    question: str = Field(default="", description="Plain-language question, e.g. 'Is there a related gene in nematodes?'")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "whatsgene-backend"}


@app.post("/jobs", status_code=201)
def create_job(body: JobCreate) -> dict:
    """Dev/test entry. The product entry point is the WhatsApp webhook."""
    raw = (body.sequence or "").strip()
    if not raw:
        raise HTTPException(status_code=422, detail="sequence is empty. Paste a FASTA sequence or an accession.")
    job = db.create_job(question=body.question or "", raw_input=raw)
    final = process_job(job, NCBIWebBackend())
    return _public_job(final)


@app.get("/jobs")
def list_jobs(limit: int = Query(default=50, le=200)) -> list[dict]:
    return [_public_job(j) for j in db.list_jobs(limit=limit)]


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    return _public_job(job)


def _public_job(job: dict) -> dict:
    """Strip server-side keys; attach step log and results metadata."""
    public = {k: v for k, v in job.items() if k != "whatsapp_user_id"}
    public["step_log"] = db.get_step_log(job["id"])
    public["results_url"] = f"{config.FRONTEND_BASE_URL}/jobs/{job['id']}"
    public["data_notice"] = (
        "Your sequence is sent to NCBI's public BLAST service. Job history is stored "
        "server-side; ask WhatsGene to 'forget my history' to delete it."
    )
    return public


# --- WhatsApp webhook (main interface, PRD §4.4) ---

@app.get("/webhooks/whatsapp")
def whatsapp_verify(request: Request) -> object:
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == config.WHATSAPP_VERIFY_TOKEN:
        return int(params.get("hub.challenge", "0"))
    raise HTTPException(status_code=403, detail="WhatsApp verification failed.")


@app.post("/webhooks/whatsapp")
async def whatsapp_inbound(request: Request) -> dict:
    payload = await request.json()
    replies: list[dict] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                sender = message.get("from", "")
                body = (message.get("text") or {}).get("body", "")
                if not sender or not body:
                    continue
                result = chat.handle_message(
                    whatsapp_user_id=sender, text=body, backend=NCBIWebBackend())
                replies.append(result)
                # Real send goes through the WhatsApp Cloud API client
                # (stub until credentials are configured); the handler's
                # reply is recorded regardless so nothing fails silently.
    return {"status": "received", "replies": replies}
