"""Agent layer — Muse Spark Open via Modal (PRD §8).

The model ONLY interprets and explains (PRD §3):
  - free text -> structured intent (contract in app/intent.py),
  - optional deviation proposals (logged; rules choice preserved
    unless DEVIATION_AUTO_APPLY is set),
  - plain-language wording of summaries and follow-ups from parsed
    facts only.
It never chooses the program directly, never decides significance,
and never invents numbers. Deterministic fallbacks keep the system
running offline / without Muse credentials.
"""
from __future__ import annotations

from .intent import parse_intent


def get_intent(question: str) -> dict:
    """Return the structured intent. Falls back to the deterministic parser."""
    # Live Muse call (OpenAI-compatible, MUSE_BASE_URL) slots in here and
    # must return the same contract; offline we use the fallback parser.
    return parse_intent(question)


def propose_deviation(*, intent: dict, detected_type: str, rules_choice: dict) -> dict | None:
    """Return a deviation proposal {program, database, reason} or None.

    No live model is wired offline, so no deviation is proposed; the
    loop still logs and applies this hook's contract when a model is
    configured.
    """
    return None


def summarise(*, job: dict, hits: list[dict], outcome: str | None,
              verification: dict | None = None) -> str:
    """Plain-language summary from parsed facts only (template fallback)."""
    program = job.get("program", "?")
    database = job.get("database", "?")
    if not hits:
        return (
            f"No hits were parsed for this job ({program} against {database}). "
            f"Outcome: {outcome or 'not confirmed'}. Every setting tried is in the step log."
        )
    top = hits[0]
    verdict = ""
    if verification:
        verdict = (
            " Reciprocal verification confirmed this candidate."
            if verification.get("confirmed")
            else f" Verification did not confirm the top candidate ({verification.get('failing_check')})."
        )
    return (
        f"Top hit: {top.get('accession', '?')} ({top.get('organism', 'unknown organism')}), "
        f"E-value {top.get('evalue', '?')}, identity {top.get('identity', '?')}%, "
        f"coverage {top.get('query_coverage', '?')}%, classified as {top.get('classification', '?')}. "
        f"Search: {program} against {database}. Outcome: {outcome or 'not confirmed'}.{verdict}"
    )


def answer_followup(*, job: dict | None, question: str) -> str:
    """Grounded follow-up: stored results + rules only (blast-rules §12).

    Quotes actual values; says so when stored results cannot answer.
    """
    if not job:
        return "You have no jobs yet. Send a sequence or an accession (e.g. NP_000509) with your question to start one."
    hits: list[dict] = job.get("hits") or []
    q = (question or "").lower()
    if "forget" in q and "history" in q:
        return "__FORGET_HISTORY__"
    if not hits:
        return (
            f"Job {job['id']} has no stored hits (status {job.get('status')}), so I can't answer that from stored results. "
            "Send a new sequence or accession to run a search."
        )
    top = hits[0]
    if any(k in q for k in ("e-value", "evalue", "significant", "confidence", "confident")):
        return (
            f"For job {job['id']}, the top hit {top.get('accession', '?')} has E-value {top.get('evalue', '?')}, "
            f"identity {top.get('identity', '?')}%, coverage {top.get('query_coverage', '?')}%, "
            f"classified as {top.get('classification', '?')} (program {job.get('program', '?')} against {job.get('database', '?')}). "
            f"Outcome: {job.get('outcome') or 'see results page'}."
        )
    if any(k in q for k in ("top hit", "best hit", "what did", "result", "found")):
        return (
            f"Top hit for job {job['id']}: {top.get('accession', '?')} ({top.get('organism', 'unknown organism')}), "
            f"E-value {top.get('evalue', '?')}, identity {top.get('identity', '?')}%, coverage {top.get('query_coverage', '?')}%, "
            f"classified as {top.get('classification', '?')}."
        )
    if any(k in q for k in ("program", "database", "why", "parameter", "settings")):
        params = job.get("parameters") or {}
        return (
            f"Job {job['id']} used {job.get('program', '?')} against {job.get('database', '?')}. "
            f"Reason recorded: {params.get('rationale', 'see step log on the results page')}"
        )
    return (
        "I can't answer that from the stored results for your latest job. "
        f"I can quote its stored values — top hit {top.get('accession', '?')}, E-value {top.get('evalue', '?')}, "
        f"identity {top.get('identity', '?')}%, coverage {top.get('query_coverage', '?')}% — or run a new search if you send a sequence."
    )
