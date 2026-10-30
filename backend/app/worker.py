"""Background worker — many workflows at once over SQLite (no queue service).

Web and WhatsApp submissions only create a queued job row; this worker
claims queued workflows and runs them in a thread pool, so several jobs
search in parallel and nobody waits on a request. NcbiRemote runs are
serialised (one in-flight RID etiquette); local/fixture runs in parallel
up to MAX_CONCURRENT_JOBS. On completion the worker WhatsApps the user.

Run standalone:  python -m app.worker
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import config, db, whatsapp_client
from .agent_loop import process_job as _run_loop
from .search_backend import get_backend

_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()
_ncbi_lock = threading.Lock()
_inflight: set[str] = set()
_inflight_lock = threading.Lock()


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=max(1, config.MAX_CONCURRENT_JOBS),
                thread_name_prefix="whatsgene-job")
        return _executor


def notify_job_done(job: dict) -> dict:
    """WhatsApp the recipient that a workflow finished. Never raises."""
    recipient = job.get("notify_to") or job.get("whatsapp_user_id")
    if not recipient or job.get("status") not in ("done", "failed"):
        return {"status": "skipped"}
    if job.get("whatsapp_status") == "sent":
        return {"status": "sent"}
    results_url = f"{config.FRONTEND_BASE_URL}/jobs/{job['id']}"
    summary = job.get("summary") or job.get("error") or f"Status: {job.get('status')}."
    result = whatsapp_client.send_job_done(
        to=str(recipient), job_id=job["id"], summary=summary, results_url=results_url)
    db.update_job(job["id"],
                  whatsapp_status="sent" if result.get("status") == "sent" else "failed",
                  notified_at=datetime.now(timezone.utc).isoformat())
    return result


def run_job(job: dict, backend=None) -> dict:
    """Run one queued workflow to completion, then notify."""
    backend = backend or get_backend()
    try:
        if backend.name == "ncbi":
            with _ncbi_lock:  # one in-flight RID, however many workflows queue
                final = _run_loop(job, backend)
        else:
            final = _run_loop(job, backend)
    finally:
        with _inflight_lock:
            _inflight.discard(job["id"])
    notify_job_done(final)
    return final


def submit_async(job: dict, backend=None) -> bool:
    """Queue a workflow on the pool. False if it is already in flight."""
    with _inflight_lock:
        if job["id"] in _inflight:
            return False
        _inflight.add(job["id"])
    _get_executor().submit(run_job, job, backend)
    return True


def drain_once(backend=None) -> int:
    """Submit every queued workflow to the pool. Returns how many started."""
    started = 0
    for job in db.list_queued_jobs(limit=50):
        if submit_async(job, backend):
            started += 1
    return started


def process_job(job: dict) -> dict:
    """Advance one job synchronously (compat for scripts and tests)."""
    return run_job(job, get_backend())


def run_forever() -> None:
    db.init_db()
    backend = get_backend()
    print(f"WhatsGene worker polling (up to {config.MAX_CONCURRENT_JOBS} workflows at once, "
          f"budget {config.MAX_SEARCHES_PER_JOB} searches / {config.MAX_JOB_SECONDS}s per job, Ctrl+C to stop)")
    while True:
        drain_once(backend)
        time.sleep(config.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_forever()
