"""WhatsGene FastAPI app — web submission, WhatsApp webhook, results API.

A submission from the website or WhatsApp only creates a queued workflow;
the background worker runs many workflows at once and WhatsApps the
result when each finishes. The web app can also ask grounded questions
about a stored workflow.

Run:
    uvicorn app.main:app --reload --port 8000
Docs: http://localhost:8000/docs
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import agent, auth, chat, config, db, whatsapp_client, worker
from .search_backend import SearchError, get_backend


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    auth.ensure_seeded_user()

    async def _drain() -> None:
        while True:
            await asyncio.to_thread(worker.drain_once)
            await asyncio.sleep(2)

    task = asyncio.create_task(_drain())
    yield
    task.cancel()


app = FastAPI(title="WhatsGene", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_BASE_URL, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class JobCreate(BaseModel):
    sequence: str = Field(description="FASTA text, raw sequence, or NCBI accession (e.g. NP_000509)")
    question: str = Field(default="", description="Plain-language question, e.g. 'Is there a related gene in nematodes?'")
    workflow_mode: str = Field(default="auto", description="auto | single | all")
    search_backend: str = Field(default="server", description="server | local | ncbi — where this workflow searches")
    program: str | None = Field(default=None, description="Program for workflow_mode=single, e.g. blastp")
    whatsapp_number: str | None = Field(default=None, description="Optional WhatsApp number for the done notification")
    source: str = Field(default="web")


class AskBody(BaseModel):
    question: str


class LoginBody(BaseModel):
    username: str
    password: str


def current_user(request: Request) -> dict:
    """Dependency: the logged-in user, or 401."""
    user = auth.resolve_session(request.cookies.get(auth.SESSION_COOKIE))
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in.")
    return {"id": user["id"], "username": user["username"]}


def _owned_job(job_id: str, user: dict) -> dict:
    """The job if owned by the caller, else 404 (never leaks existence)."""
    job = db.get_job(job_id)
    if not job or job.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    return job


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "whatsgene-backend"}


@app.post("/auth/login")
def login(body: LoginBody, response: Response) -> dict:
    user = db.get_user_by_username((body.username or "").strip())
    if not user or not auth.verify_password(body.password or "", user["password_hash"]):
        raise HTTPException(status_code=401, detail="Wrong username or password.")
    token = auth.create_session_token()
    db.create_session(user["id"], token, auth.session_expiry_iso())
    response.set_cookie(auth.SESSION_COOKIE, token, httponly=True, samesite="lax",
                        secure=config.COOKIE_SECURE, max_age=auth.cookie_max_age(), path="/")
    return {"username": user["username"]}


@app.post("/auth/logout")
def logout(request: Request, response: Response) -> dict:
    token = request.cookies.get(auth.SESSION_COOKIE)
    if token:
        db.delete_session(token)
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return {"status": "logged out"}


@app.get("/auth/me")
def me(request: Request) -> dict:
    user = auth.resolve_session(request.cookies.get(auth.SESSION_COOKIE))
    if not user:
        return {"authenticated": False}
    return {"authenticated": True, "username": user["username"]}


@app.get("/privacy")
def privacy() -> dict:
    """Public privacy policy (Meta app publishing requirement)."""
    return {
        "service": "WhatsGene",
        "summary": (
            "WhatsGene is a research and education tool, not medical advice. "
            "We store your submitted sequence/accession, question, search parameters "
            "(program, database, E-value threshold, word size, matrix), parsed hits, "
            "and step log so results can be shown and follow-up questions answered "
            "from stored values. Your WhatsApp number is stored server-side only as "
            "your job-history key and is never shown on results pages. Local searches "
            "run on our server; remote searches send the sequence to NCBI's public "
            "BLAST service. Message 'forget my history' on WhatsApp at any time to "
            "delete your stored job history."
        ),
        "contact": "junxun288@gmail.com",
    }


@app.post("/jobs", status_code=201)
def create_job(body: JobCreate, user: dict = Depends(current_user)) -> dict:
    """Queue a workflow and return at once; the worker runs it."""
    raw = (body.sequence or "").strip()
    if not raw:
        raise HTTPException(status_code=422, detail="sequence is empty. Paste a FASTA sequence or an accession.")
    mode = (body.workflow_mode or "auto").lower()
    if mode not in ("auto", "single", "all"):
        raise HTTPException(status_code=422, detail="workflow_mode must be auto, single, or all.")
    if db.get_usage(user["id"], db.today_iso(), "jobs") >= config.JOBS_DAILY_LIMIT:
        raise HTTPException(status_code=429,
                            detail=f"Daily search limit reached ({config.JOBS_DAILY_LIMIT}/day).")
    notify = (body.whatsapp_number or "").strip() or None
    job = db.create_job(question=body.question or "", raw_input=raw,
                        whatsapp_user_id=notify, source=body.source or "web",
                        workflow_mode=mode, requested_program=body.program,
                        notify_to=notify, backend_choice=(body.search_backend or "server"),
                        user_id=user["id"])
    db.bump_usage(user["id"], db.today_iso(), "jobs")
    try:
        backend = worker.backend_for_job(job)
    except SearchError as exc:
        # Queue anyway only if a worker could succeed later; surface config
        # errors now so the user is not left waiting on a dead workflow.
        db.update_job(job["id"], status="failed", error=str(exc), summary=str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if backend.name == "fixture":
        final = worker.run_job(job, backend)  # recorded data finishes instantly
        return _public_job(final, user["id"])
    worker.submit_async(job, backend)
    return _public_job(db.get_job(job["id"]) or job, user["id"])


@app.get("/jobs")
def list_jobs(limit: int = Query(default=50, le=200),
              user: dict = Depends(current_user)) -> list[dict]:
    return [_public_job(j, user["id"]) for j in db.list_jobs(limit=limit, user_id=user["id"])]


@app.get("/jobs/{job_id}")
def get_job(job_id: str, user: dict = Depends(current_user)) -> dict:
    return _public_job(_owned_job(job_id, user), user["id"])


@app.post("/jobs/{job_id}/align")
def align_job(job_id: str, user: dict = Depends(current_user)) -> dict:
    """Tier 2: MSA + neighbor-joining tree from confirmed homologs."""
    from .msa import MsaError, run_alignment

    job = _owned_job(job_id, user)
    if job["status"] != "done":
        raise HTTPException(status_code=409, detail="Alignment needs a finished workflow.")
    try:
        backend = get_backend()
    except SearchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        final = run_alignment(job=job, search_backend=backend)
    except MsaError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _public_job(final, user["id"])


@app.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, user: dict = Depends(current_user)) -> dict:
    job = _owned_job(job_id, user)
    if job["status"] in ("done", "failed", "cancelled"):
        return _public_job(job, user["id"])
    return _public_job(db.update_job(job_id, status="cancelled") or job, user["id"])


@app.delete("/jobs/{job_id}")
def delete_job(job_id: str, user: dict = Depends(current_user)) -> dict:
    """Delete a finished workflow and its stored searches + step log."""
    _owned_job(job_id, user)
    job = db.get_job(job_id)
    assert job is not None
    if job["status"] in ("queued", "running"):
        raise HTTPException(status_code=409,
                            detail="This workflow is still running. Cancel it before deleting.")
    db.delete_job(job_id)
    return {"status": "deleted", "id": job_id}


@app.post("/jobs/{job_id}/ask")
def ask_job(job_id: str, body: AskBody, user: dict = Depends(current_user)) -> dict:
    """Grounded Q&A over this workflow's stored results (web Ask box)."""
    job = _owned_job(job_id, user)
    try:
        answer = agent.answer_followup(job=job, question=body.question,
                                       searches=db.get_searches(job_id),
                                       user_id=user["id"])
    except agent.QuotaError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    if answer == "__FORGET_HISTORY__":
        return {"job_id": job_id, "answer": "Ask on WhatsApp to delete chat history, or use a job you own there."}
    return {"job_id": job_id, "answer": answer}


def _public_job(job: dict, user_id: int | None = None) -> dict:
    """Strip server-side keys; attach searches, step log, metadata."""
    public = {k: v for k, v in job.items()
              if k not in ("whatsapp_user_id", "notify_to", "user_id")}
    public["step_log"] = db.get_step_log(job["id"])
    public["searches"] = db.get_searches(job["id"])
    public["related_jobs"] = [
        {"id": r["id"], "question": r.get("question"), "status": r.get("status"),
         "outcome": r.get("outcome"), "program": r.get("program"),
         "created_at": r.get("created_at")}
        for r in db.related_jobs(job, user_id=user_id)]
    public["notify_configured"] = bool(job.get("notify_to") or job.get("whatsapp_user_id"))
    public["results_url"] = f"{config.FRONTEND_BASE_URL}/jobs/{job['id']}"
    backend_name = (job.get("parameters") or {}).get("backend", "ncbi")
    history = "Job history is stored server-side; ask WhatsGene to 'forget my history' to delete it."
    if backend_name == "local":
        public["data_notice"] = (
            "Your sequence was searched against a database on this server; "
            f"nothing was sent to NCBI. {history}"
        )
    elif backend_name == "fixture":
        public["data_notice"] = f"Demo results from recorded data; no live search ran. {history}"
    else:
        public["data_notice"] = (
            f"Your sequence was sent to NCBI's public BLAST service. {history}"
        )
    return public


# --- WhatsApp webhook ---

@app.get("/webhooks/whatsapp")
def whatsapp_verify(request: Request) -> object:
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == config.WHATSAPP_VERIFY_TOKEN:
        return int(params.get("hub.challenge", "0"))
    raise HTTPException(status_code=403, detail="WhatsApp verification failed.")


@app.post("/webhooks/whatsapp")
async def whatsapp_inbound(request: Request) -> dict:
    payload = await request.json()
    # TEMP DEBUG (delivery diagnosis): record every webhook payload,
    # including message statuses with Meta's failure reasons.
    try:
        import json as _json
        from pathlib import Path as _Path

        with _Path("/tmp/whatsgene-webhooks.log").open("a", encoding="utf-8") as fh:
            fh.write(_json.dumps(payload) + "\n")
    except Exception:
        pass
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
                    whatsapp_user_id=sender, text=body, backend=get_backend())
                replies.append(result)
                sent = whatsapp_client.send_text(to=sender, body=result.get("reply", ""))
                if result.get("job_id"):
                    job = db.get_job(result["job_id"])
                    if job and job.get("status") in ("done", "failed"):
                        db.update_job(job["id"],
                                      whatsapp_status="sent" if sent.get("status") == "sent" else "failed")
    return {"status": "received", "replies": replies}
