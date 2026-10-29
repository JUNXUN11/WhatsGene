"""Background worker — polling loop over SQLite (PRD §8, no queue service).

The per-job work lives in app.agent_loop.process_job; this module owns
the polling loop and the live NCBI backend. Run standalone:

    python -m app.worker
"""
from __future__ import annotations

import time

from . import config, db
from .agent_loop import process_job as _run_loop
from .blast_backend import NCBIWebBackend


def process_job(job: dict) -> dict:
    """Advance one queued job with the live NCBI backend."""
    return _run_loop(job, NCBIWebBackend())


def run_forever() -> None:
    db.init_db()
    backend = NCBIWebBackend()
    print(f"WhatsGene worker polling (budget {config.MAX_SEARCHES_PER_JOB} searches / "
          f"{config.MAX_JOB_SECONDS}s per job, Ctrl+C to stop)")
    while True:
        for job in db.list_jobs(limit=50):
            if job["status"] == "queued":
                _run_loop(job, backend)
        time.sleep(config.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_forever()
