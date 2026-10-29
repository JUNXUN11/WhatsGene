"""WhatsApp chat handling (PRD §4.4, main interface).

A message containing a sequence or accession starts a new job; other
messages are follow-up questions about stored results (default: latest
job). One running job per chat: a new sequence during a run gets a
"job running" reply offering cancel — it never replaces the run.
"""
from __future__ import annotations

import re

from . import agent, db
from .agent_loop import process_job
from .blast_backend import BlastBackend
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


def handle_message(*, whatsapp_user_id: str, text: str, backend: BlastBackend) -> dict:
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
        running = db.running_job_for_user(whatsapp_user_id)
        if running:
            return {"action": "job_running", "job_id": running["id"],
                    "reply": (f"A job is already running in this chat ({running['id']}, status {running['status']}). "
                              "Reply 'cancel' to stop it, then send the new sequence.")}
        job = db.create_job(question=question, raw_input=sequence_text,
                            whatsapp_user_id=whatsapp_user_id)
        final = process_job(job, backend)
        if final.get("status") == "failed":
            reply = f"Job {final['id']} could not run: {final.get('error')}"
        else:
            reply = (f"Job {final['id']} done ({final.get('outcome')}). {final.get('summary', '')} "
                     f"Full results: /jobs/{final['id']}")
        return {"action": "job", "job_id": final["id"], "reply": reply}

    # Follow-up question: grounded in stored results only.
    latest = db.latest_job_for_user(whatsapp_user_id)
    answer = agent.answer_followup(job=latest, question=body)
    if answer == "__FORGET_HISTORY__":
        count = db.delete_user_history(whatsapp_user_id)
        return {"action": "forgot_history", "job_id": None,
                "reply": f"Done — deleted your stored job history ({count} job(s))."}
    return {"action": "followup", "job_id": latest["id"] if latest else None, "reply": answer}
