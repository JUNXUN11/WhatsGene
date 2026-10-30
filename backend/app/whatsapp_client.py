"""WhatsApp Cloud API client.

A WhatsApp failure never fails the job; the results page stays the
source of truth and the job row records whatsapp_status instead.
Inside the 24-hour window a text message is sent; send_job_done can
fall back to the pre-approved utility template outside it.
"""
from __future__ import annotations

from . import config

_GRAPH = "https://graph.facebook.com/v21.0"


def build_text_payload(*, to: str, body: str) -> dict:
    return {"messaging_product": "whatsapp", "to": to,
            "type": "text", "text": {"body": body}}


def build_template_payload(*, to: str, job_id: str) -> dict:
    return {"messaging_product": "whatsapp", "to": to, "type": "template",
            "template": {"name": config.WHATSAPP_TEMPLATE_NAME, "language": {"code": "en"},
                         "components": [{"type": "body", "parameters": [
                             {"type": "text", "text": job_id}]}]}}


def _post(payload: dict) -> dict:
    if not config.WHATSAPP_TOKEN or not config.WHATSAPP_PHONE_NUMBER_ID:
        return {"status": "failed",
                "reason": "WhatsApp not configured (WHATSAPP_TOKEN / WHATSAPP_PHONE_NUMBER_ID missing)"}
    import httpx

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{_GRAPH}/{config.WHATSAPP_PHONE_NUMBER_ID}/messages",
                json=payload,
                headers={"Authorization": f"Bearer {config.WHATSAPP_TOKEN}"})
            response.raise_for_status()
    except Exception as exc:  # network/API failure never fails the job
        return {"status": "failed", "reason": f"WhatsApp send failed: {exc}"}
    return {"status": "sent"}


def send_text(*, to: str, body: str) -> dict:
    """Send a free-text message (valid inside the 24-hour window)."""
    if not to:
        return {"status": "failed", "reason": "No WhatsApp recipient stored for this job."}
    return _post(build_text_payload(to=to, body=body))


def send_job_done(*, to: str, job_id: str, summary: str, results_url: str) -> dict:
    """Notify that a workflow finished, with summary + results link."""
    if not to:
        return {"status": "failed", "reason": "No WhatsApp recipient stored for this job."}
    body = f"WhatsGene job {job_id} is done. {summary} Full results: {results_url}"
    result = _post(build_text_payload(to=to, body=body))
    if result["status"] == "sent":
        return result
    # Outside the 24-hour window a text message is rejected; the utility
    # template opens the conversation with the job ID.
    template = _post(build_template_payload(to=to, job_id=job_id))
    if template["status"] == "sent":
        return {"status": "sent", "via": "template"}
    return result
