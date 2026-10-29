"""WhatsApp Cloud API client (FR9). Boilerplate stub — real send lands 2 Nov.

Failure rule (docs/ARCHITECTURE.md): a WhatsApp failure never fails the
job itself; the results page stays the source of truth.
"""
from __future__ import annotations

from . import config


def send_job_done(*, to: str, job_id: str, summary: str, results_url: str) -> dict:
    """Send the job-done notification. Returns a status dict. TODO (2 Nov)."""
    if not config.WHATSAPP_TOKEN or not config.WHATSAPP_PHONE_NUMBER_ID:
        return {"status": "failed", "reason": "WhatsApp not configured (WHATSAPP_TOKEN / WHATSAPP_PHONE_NUMBER_ID missing)"}
    raise NotImplementedError("TODO 2 Nov: WhatsApp Cloud API send (template outside 24h window)")
