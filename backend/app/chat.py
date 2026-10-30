"""WhatsApp chat handling (main interface).

A message containing a sequence or accession starts a new workflow;
other messages are follow-up questions about stored results (default:
latest job, or the job named as WG-... in the message). Many workflows
may run at once for the same chat — a new sequence never waits for or
replaces a running one. When a workflow finishes, the worker WhatsApps
the result in this thread.
"""
from __future__ import annotations

import re

from . import agent, db
from .agent_loop import process_job
from .search_backend import SearchBackend
from .validate import looks_like_accession

_SEQ_LINE = re.compile(r"^[A-Za-z\-*\s]+$")


def extract_sequence_and_question(text: str) -> tuple[str | None, str]:
    """Split a chat message into (sequence_text, question_text).

    Handles: bare accession ("NP_000509 ...question"), FASTA blocks,
    and raw sequence lines. Returns (None, text) for pure follow-ups.
    """
    raw = (text or "").strip()
    if not raw:
        return None, ""
    first = raw.split()[0].strip(",")
    if looks_like_accession(first):
        return first, raw[len(raw.split()[0]):].strip(" ?.!,")
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    seq_lines: list[str] = []
    question_lines: list[str] = []
    in_fasta = False
    for line in lines:
        if line.startswith(">"):
            in_fasta = True
            seq_lines.append(line)
            continue
        is_seq = bool(_SEQ_LINE.match(line)) and sum(c.isalpha() for c in line) >= 10 \
            and len(line.split()) <= 3
        if in_fasta or (is_seq and not question_lines):
            seq_lines.append(line)
            in_fasta = in_fasta or is_seq
        else:
            question_lines.append(line)
    if seq_lines and any(len(ln.replace(">", "")) >= 10 or ln.startswith(">") for ln in seq_lines):
        return "\n".join(seq_lines), " ".join(question_lines)
    return None, raw


def handle_message(*, whatsapp_user_id: str, text: str, backend: SearchBackend) -> dict:
    """Handle one inbound message. Returns {action, reply, job_id}."""
    body = (text or "").strip()
    low = body.lower()

    if low in ("cancel", "cancel job", "stop", "stop job"):
        running = db.running_job_for_user(whatsapp_user_id)
        if running:
            db.update_job(running["id"], status="cancelled")
            return {"action": "cancelled", "job_id": running["id"],
                    "reply": f"Job {running['id']} cancelled. Send a new sequence whenever you're ready."}
        return {"action": "followup", "job_id": None, "reply": "No job is running in this chat."}

    if "forget" in low and "history" in low:
        count = db.delete_user_history(whatsapp_user_id)
        return {"action": "forgot_history", "job_id": None,
                "reply": f"Done — deleted your stored job history ({count} job(s)). Nothing is kept for this chat now."}

    sequence_text, question = extract_sequence_and_question(body)

    if sequence_text is not None:
        job = db.create_job(question=question, raw_input=sequence_text,
                            whatsapp_user_id=whatsapp_user_id, source="whatsapp")
        if backend.name == "fixture":
            # Recorded-data runs finish instantly; tests and demos see the
            # result in this same reply. Live backends run in the background.
            final = process_job(job, backend)
            if final.get("status") == "failed":
                reply = f"Job {final['id']} could not run: {final.get('error')}"
            else:
                reply = (f"Job {final['id']} done ({final.get('outcome')}). {final.get('summary', '')} "
                         f"Full results: /jobs/{final['id']}")
            return {"action": "job", "job_id": final["id"], "reply": reply}
        from . import worker

        worker.submit_async(job, backend)
        running = len([j for j in db.list_jobs_for_user(whatsapp_user_id)
                       if j["status"] in ("queued", "running")])
        return {"action": "job_queued", "job_id": job["id"],
                "reply": (f"Job {job['id']} is queued and running in the background "
                          f"({running} workflow(s) active in this chat). You can send another "
                          "sequence now — I will WhatsApp you here as each one finishes.")}

    # Follow-up question: grounded in stored results only. A WG-... ID in
    # the message selects that workflow; otherwise the latest one is used.
    match = re.search(r"(WG-[A-Z0-9\-]+)", body, re.IGNORECASE)
    target = db.get_job(match.group(1).upper()) if match else None
    latest = target or db.latest_job_for_user(whatsapp_user_id)
    if latest and "status" in low:
        return {"action": "followup", "job_id": latest["id"],
                "reply": (f"Job {latest['id']} is {latest.get('status')}"
                          f" (outcome: {latest.get('outcome') or 'pending'}). "
                          f"Full results: /jobs/{latest['id']}")}
    answer = agent.answer_followup(
        job=latest, question=body,
        searches=db.get_searches(latest["id"]) if latest else None)
    if answer == "__FORGET_HISTORY__":
        count = db.delete_user_history(whatsapp_user_id)
        return {"action": "forgot_history", "job_id": None,
                "reply": f"Done — deleted your stored job history ({count} job(s))."}
    return {"action": "followup", "job_id": latest["id"] if latest else None, "reply": answer}
