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
              verification: dict | None = None,
              workflow_searches: list[dict] | None = None) -> str:
    """Plain-language summary from parsed facts only (template fallback)."""
    program = job.get("program", "?")
    database = job.get("database", "?")
    verdict = ""
    if verification:
        verdict = (
            " Reciprocal verification confirmed this candidate."
            if verification.get("confirmed")
            else f" Verification did not confirm the top candidate ({verification.get('failing_check')})."
        )
    if workflow_searches and len(workflow_searches) > 1:
        parts = []
        for search in workflow_searches:
            shits = search.get("hits") or []
            if shits:
                t = shits[0]
                parts.append(f"{search.get('program')}: top hit {t.get('accession', '?')} "
                             f"E-value {t.get('evalue', '?')}, {t.get('classification', '?')}")
            else:
                parts.append(f"{search.get('program')}: no hits")
        return (f"Workflow ran {len(workflow_searches)} programs. " + "; ".join(parts) +
                f". Outcome: {outcome or 'not confirmed'}.{verdict}")
    if not hits:
        return (
            f"No hits were parsed for this job ({program} against {database}). "
            f"Outcome: {outcome or 'not confirmed'}. Every setting tried is in the step log."
        )
    top = hits[0]
    return (
        f"Top hit: {top.get('accession', '?')} ({top.get('organism', 'unknown organism')}), "
        f"E-value {top.get('evalue', '?')}, identity {top.get('identity', '?')}%, "
        f"coverage {top.get('query_coverage', '?')}%, classified as {top.get('classification', '?')}. "
        f"Search: {program} against {database}. Outcome: {outcome or 'not confirmed'}.{verdict}"
    )


def answer_followup(*, job: dict | None, question: str,
                    searches: list[dict] | None = None) -> str:
    """Grounded follow-up: stored results + rules only (blast-rules §12)."""
    from .qa import answer_question

    return answer_question(job=job, searches=searches, question=question)
