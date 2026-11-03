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
from pathlib import Path

from fastapi import (APIRouter, Depends, FastAPI, HTTPException, Query,
                     Request, Response)
from fastapi.responses import FileResponse
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import (agent, auth, chat, config, db, library, setup_runner,
               settings as user_settings, whatsapp_client, worker)
from .search_backend import (SearchError, get_backend, get_backend_for_choice,
                             local_database_catalog, local_database_entry)


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

# Every API route lives on this router. It is included twice at the end
# of this file: at the root (tests, tunnel, hosted frontend) and under
# /api (the One Box frontend, which calls its own origin).
api = APIRouter()


class JobCreate(BaseModel):
    sequence: str = Field(description="FASTA text, raw sequence, or NCBI accession (e.g. NP_000509)")
    question: str = Field(default="", description="Plain-language question, e.g. 'Is there a related gene in nematodes?'")
    workflow_mode: str = Field(default="auto", description="auto | single | all")
    search_backend: str = Field(default="server", description="server | local | ncbi — where this workflow searches")
    database: str | None = Field(default=None, description="Canonical local database name (e.g. pdbaa, 16s_rrna); empty = rules engine chooses")
    program: str | None = Field(default=None, description="Program for workflow_mode=single, e.g. blastp")
    whatsapp_number: str | None = Field(default=None, description="Optional WhatsApp number for the done notification")
    source: str = Field(default="web")


class AskBody(BaseModel):
    question: str


class LoginBody(BaseModel):
    username: str
    password: str


class SettingsBody(BaseModel):
    lab_name: str = ""
    default_organism: str = ""
    default_backend: str = "server"
    strictness: str = "balanced"
    cutoff_mode: str = "standard"
    cutoffs: dict | None = None
    muse_api_key: str = ""
    clear_muse_key: bool = False
    muse_base_url: str = ""
    muse_model: str = ""


class AiSetupBody(BaseModel):
    database: str = "swissprot"
    message: str = ""


class LibrarySortBody(BaseModel):
    items: list[dict] = Field(default_factory=list,
                              description="[{path, category}] confirmed by the user")


class LibraryBuildBody(BaseModel):
    root: str = Field(default="library", description="inbox | library")
    path: str = Field(description="File path as returned by GET /library")
    name: str = Field(description="Custom database name, e.g. worm_globins")


class TaxonBuildBody(BaseModel):
    organism: str = Field(description="Organism or taxon, e.g. C. elegans")
    name: str = Field(description="Custom database name, e.g. celegans_proteins")


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


@api.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "whatsgene-backend"}


@api.post("/auth/login")
def login(body: LoginBody, response: Response) -> dict:
    user = db.get_user_by_username((body.username or "").strip())
    if not user or not auth.verify_password(body.password or "", user["password_hash"]):
        raise HTTPException(status_code=401, detail="Wrong username or password.")
    token = auth.create_session_token()
    db.create_session(user["id"], token, auth.session_expiry_iso())
    # Split hosting (frontend and API on different sites) needs
    # SameSite=None; browsers reject that without Secure, so force it.
    samesite = config.COOKIE_SAMESITE
    response.set_cookie(auth.SESSION_COOKIE, token, httponly=True, samesite=samesite,
                        secure=config.COOKIE_SECURE or samesite == "none",
                        max_age=auth.cookie_max_age(), path="/")
    return {"username": user["username"]}


@api.post("/auth/logout")
def logout(request: Request, response: Response) -> dict:
    token = request.cookies.get(auth.SESSION_COOKIE)
    if token:
        db.delete_session(token)
    samesite = config.COOKIE_SAMESITE
    response.delete_cookie(auth.SESSION_COOKIE, path="/", samesite=samesite,
                           secure=config.COOKIE_SECURE or samesite == "none")
    return {"status": "logged out"}


@api.get("/auth/me")
def me(request: Request) -> dict:
    user = auth.resolve_session(request.cookies.get(auth.SESSION_COOKIE))
    if not user:
        return {"authenticated": False}
    return {"authenticated": True, "username": user["username"]}


@api.get("/settings")
def get_settings(user: dict = Depends(current_user)) -> dict:
    """The caller's customization profile, presets, and setup status."""
    return user_settings.public_settings(user["id"])


@api.put("/settings")
def put_settings(body: SettingsBody, user: dict = Depends(current_user)) -> dict:
    try:
        saved = user_settings.save_settings(user["id"], body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"settings": saved, **user_settings.muse_key_hint(user["id"])}


@api.post("/settings/ai-setup")
def ai_setup(body: AiSetupBody, user: dict = Depends(current_user)) -> dict:
    """Muse-guided local BLAST setup (plan + explanation).

    With the user's own Muse key, a live model explains the deterministic
    plan; without one (or on any model failure) the scripted demo reply is
    returned. Execution lives in POST /setup/run (fixed code, no model).
    """
    plan = user_settings.setup_plan(body.database or "swissprot")
    reply = user_settings.setup_assistant_reply(
        database_choice=plan["database"], question=body.message or "", plan=plan)
    mode = "demo"
    key = user_settings.get_muse_key(user["id"])
    if key:
        profile = user_settings.get_settings(user["id"])
        from .model_client import ModelError, chat_completion

        facts = "\n".join(
            f"- {s['title']}: {s['status']} — {s['detail']}" for s in plan["steps"])
        try:
            result = chat_completion(
                system=("You are the WhatsGene setup assistant for wet-lab scientists. "
                        "Explain the given local BLAST setup plan in plain language, short "
                        "sentences. Use only the facts given; never invent commands, "
                        "thresholds, or results."),
                user=f"SETUP FACTS:\n{facts}\n\nUSER MESSAGE: {(body.message or 'Help me set up local BLAST.')[:500]}",
                max_tokens=config.MODEL_MAX_TOKENS, api_key=key,
                base_url=profile.get("muse_base_url") or None,
                model=profile.get("muse_model") or None)
            reply = result["text"]
            mode = "live"
        except ModelError:
            mode = "demo"  # scripted reply already prepared above
    return {"reply": reply, "mode": mode, "plan": plan}


class SetupRunBody(BaseModel):
    database: str = "swissprot"


@api.post("/setup/run", status_code=202)
def run_setup(body: SetupRunBody, user: dict = Depends(current_user)) -> dict:
    """Run real local setup (download, build, verify) in the background.

    Muse explains the plan; setup_runner executes fixed steps and
    reports live state. One run at a time; a second POST while running
    returns the running state instead of starting a duplicate.
    """
    if (body.database or "swissprot") != "swissprot":
        raise HTTPException(status_code=422,
                            detail="This wizard builds the SwissProt copy today. "
                                   "Custom files go through the Library page.")
    if setup_runner.is_running():
        return setup_runner.get_state()
    return setup_runner.start(body.database or "swissprot")


@api.get("/setup/status")
def setup_status(user: dict = Depends(current_user)) -> dict:
    return setup_runner.get_state()


@api.get("/privacy")
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


def _library_root(root: str):
    if root == "inbox":
        return library.inbox_dir()
    if root == "library":
        return library.library_dir()
    raise HTTPException(status_code=422, detail="root must be inbox or library.")


@api.get("/library")
def get_library(user: dict = Depends(current_user)) -> dict:
    """Inbox inventory + sorted library for the file-drop page."""
    return {
        "inbox_dir": str(library.inbox_dir()),
        "library_dir": str(library.library_dir()),
        "inbox": library.inventory(),
        "library": library.library_inventory(),
    }


@api.post("/library/sort")
def sort_library(body: LibrarySortBody, user: dict = Depends(current_user)) -> dict:
    """Copy user-confirmed inbox files into the library. Never moves."""
    try:
        return library.sort_files(body.items)
    except (ValueError, library.LibraryError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@api.post("/library/build-database")
def build_database(body: LibraryBuildBody, user: dict = Depends(current_user)) -> dict:
    """Build a small custom BLAST database from one sorted FASTA file."""
    try:
        source = library.resolve_within(_library_root(body.root), body.path)
        return library.build_custom_database(source, body.name)
    except (ValueError, library.LibraryError, SearchError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@api.post("/library/build-from-taxon")
def build_from_taxon(body: TaxonBuildBody, user: dict = Depends(current_user)) -> dict:
    """Build a small custom database: one taxon's SwissProt subset."""
    try:
        return library.build_database_from_taxon(body.organism, body.name)
    except (ValueError, library.LibraryError, SearchError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@api.get("/library/query-text")
def library_query_text(root: str = "library", path: str = "",
                       user: dict = Depends(current_user)) -> dict:
    """First searchable record of a sorted file, for one-click search."""
    try:
        source = library.resolve_within(_library_root(root), path)
        return {"text": library.read_query_text(source)}
    except (ValueError, library.LibraryError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@api.get("/databases")
def list_databases(user: dict = Depends(current_user)) -> dict:
    """Local databases a workflow can name, with built/not-built status."""
    return {"databases": local_database_catalog()}


@api.post("/jobs", status_code=201)
def create_job(body: JobCreate, user: dict = Depends(current_user)) -> dict:
    """Queue a workflow and return at once; the worker runs it."""
    raw = (body.sequence or "").strip()
    if not raw:
        raise HTTPException(status_code=422, detail="sequence is empty. Paste a FASTA sequence or an accession.")
    mode = (body.workflow_mode or "auto").lower()
    if mode not in ("auto", "single", "all"):
        raise HTTPException(status_code=422, detail="workflow_mode must be auto, single, or all.")
    requested_db = (body.database or "").strip() or None
    if requested_db:
        entry = local_database_entry(requested_db)
        if entry is None:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown local database {requested_db!r}. "
                       "Choose one from GET /databases, or leave it automatic.")
        if mode == "all":
            raise HTTPException(
                status_code=422,
                detail="A specific database cannot be combined with All programs. "
                       "Choose Auto or one program with that database.")
        try:
            backend_name = get_backend_for_choice(body.search_backend or "server").name
        except SearchError:
            backend_name = None  # existing post-queue check reports config errors
        if backend_name == "ncbi":
            raise HTTPException(
                status_code=422,
                detail=f"Local database {requested_db} needs the Local BLAST "
                       "search location. Choose Local BLAST, or clear the database.")
        if backend_name == "local":
            ready = {d["name"]: d["ready"] for d in local_database_catalog()}
            if not ready.get(requested_db):
                raise HTTPException(
                    status_code=503,
                    detail=f"Local database {requested_db} is not built on this "
                           "machine yet. Build it first (see README), or clear the database.")
    if db.get_usage(user["id"], db.today_iso(), "jobs") >= config.JOBS_DAILY_LIMIT:
        raise HTTPException(status_code=429,
                            detail=f"Daily search limit reached ({config.JOBS_DAILY_LIMIT}/day).")
    notify = (body.whatsapp_number or "").strip() or None
    # Snapshot the caller's strictness preset onto the job: later Settings
    # changes must not rewrite what a running/finished workflow used.
    profile = user_settings.get_settings(user["id"])
    job = db.create_job(question=body.question or "", raw_input=raw,
                        whatsapp_user_id=notify, source=body.source or "web",
                        workflow_mode=mode, requested_program=body.program,
                        requested_database=requested_db,
                        notify_to=notify, backend_choice=(body.search_backend or "server"),
                        user_id=user["id"], strictness=profile["strictness"],
                        cutoffs=user_settings.job_cutoffs(profile))
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


@api.get("/jobs")
def list_jobs(limit: int = Query(default=50, le=200),
              user: dict = Depends(current_user)) -> list[dict]:
    return [_public_job(j, user["id"]) for j in db.list_jobs(limit=limit, user_id=user["id"])]


@api.get("/jobs/{job_id}")
def get_job(job_id: str, user: dict = Depends(current_user)) -> dict:
    return _public_job(_owned_job(job_id, user), user["id"])


@api.post("/jobs/{job_id}/align")
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


@api.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, user: dict = Depends(current_user)) -> dict:
    job = _owned_job(job_id, user)
    if job["status"] in ("done", "failed", "cancelled"):
        return _public_job(job, user["id"])
    return _public_job(db.update_job(job_id, status="cancelled") or job, user["id"])


@api.delete("/jobs/{job_id}")
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


@api.post("/jobs/{job_id}/ask")
def ask_job(job_id: str, body: AskBody, user: dict = Depends(current_user)) -> dict:
    """Grounded Q&A over this workflow's stored results (web Ask box)."""
    job = _owned_job(job_id, user)
    try:
        profile = user_settings.get_settings(user["id"])
        answer = agent.answer_followup(job=job, question=body.question,
                                       searches=db.get_searches(job_id),
                                       user_id=user["id"],
                                       muse_api_key=user_settings.get_muse_key(user["id"]),
                                       muse_base_url=profile.get("muse_base_url") or None,
                                       muse_model=profile.get("muse_model") or None)
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

@api.get("/webhooks/whatsapp")
def whatsapp_verify(request: Request) -> object:
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == config.WHATSAPP_VERIFY_TOKEN:
        return int(params.get("hub.challenge", "0"))
    raise HTTPException(status_code=403, detail="WhatsApp verification failed.")


@api.post("/webhooks/whatsapp")
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


# Root paths keep tests, the tunnel, and the hosted frontend working.
# The /api copy serves the One Box frontend from the same origin.
app.include_router(api)
app.include_router(api, prefix="/api")


def _frontend_dist() -> Path | None:
    """Built frontend dir, or None when the box ships API-only."""
    raw = config.FRONTEND_DIST or str(
        Path(__file__).resolve().parent.parent.parent
        / "frontend" / ".output" / "public")
    dist = Path(raw)
    return dist if (dist / "index.html").is_file() else None


_FRONTEND_DIST = _frontend_dist()


class _SpaMiddleware(BaseHTTPMiddleware):
    """One Box: page addresses win for browsers, API wins for API calls.

    Page and API paths overlap (/jobs, /library, /settings, /jobs/{id}),
    so routing alone cannot split them. Browsers navigating send
    Accept: text/html; API clients ($fetch, curl, tests) do not. For an
    HTML-accepting GET outside /api/* and the docs, serve the matching
    built file (/jobs/ → jobs/index.html), the app shell for dynamic job
    pages, and otherwise fall through to the app (API or 404).
    """

    async def dispatch(self, request: Request, call_next):
        if (_FRONTEND_DIST is not None and request.method == "GET"
                and "text/html" in request.headers.get("accept", "")):
            path = request.url.path
            if not path.startswith(("/api/", "/api", "/docs", "/redoc", "/openapi.json")):
                try:
                    target = library.resolve_within(_FRONTEND_DIST, path.lstrip("/"))
                except ValueError:
                    target = None
                if target is not None and target.is_file():
                    return FileResponse(target)
                if target is not None and target.is_dir():
                    index = target / "index.html"
                    if index.is_file():
                        return FileResponse(index)
                if path.startswith("/jobs/"):
                    return FileResponse(_FRONTEND_DIST / "index.html")
        return await call_next(request)


app.add_middleware(_SpaMiddleware)


@app.get("/{spa_path:path}", include_in_schema=False)
async def serve_frontend(spa_path: str):
    """One Box: serve the built site. Registered last, so every API
    route wins. Unknown pages fall back to the app shell (client-side
    routing); unknown /api/* paths stay honest JSON 404s."""
    if _FRONTEND_DIST is None:
        raise HTTPException(status_code=404, detail="Frontend not built. Run: cd frontend && npm run generate")
    if spa_path.startswith("api/") or spa_path == "api":
        raise HTTPException(status_code=404, detail=f"No such API path: /{spa_path}")
    try:
        target = library.resolve_within(_FRONTEND_DIST, spa_path)
    except ValueError:
        target = _FRONTEND_DIST / "index.html"
    if spa_path and target.is_file():
        return FileResponse(target)
    fallback = _FRONTEND_DIST / "200.html"
    return FileResponse(fallback if fallback.is_file() else _FRONTEND_DIST / "index.html")
