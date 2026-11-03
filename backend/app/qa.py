"""Grounded Q&A over stored workflow results (blast-rules §12).

Answers come only from the job row, its stored searches (exact
parameters + parsed hits per program) and fixed code thresholds. If the
stored results cannot answer, the reply says so — no value is invented.
Used by both WhatsApp follow-ups and the web Ask box.
"""
from __future__ import annotations

from . import config
from .blast_params import NCBI_DEFAULTS


def _fmt(value) -> str:
    if value is None or value == "":
        return "?"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _primary_searches(searches: list[dict]) -> list[dict]:
    return [s for s in searches if s.get("kind") in ("primary", "retry")]


def _top(search: dict) -> dict | None:
    hits = search.get("hits") or []
    return hits[0] if hits else None


def answer_question(*, job: dict | None, searches: list[dict] | None,
                    question: str) -> str:
    if not job:
        return ("You have no jobs yet. Send a sequence or an accession "
                "(e.g. NP_000509) with your question to start one.")
    q = (question or "").lower()
    if "forget" in q and "history" in q:
        return "__FORGET_HISTORY__"
    searches = searches or []
    primaries = _primary_searches(searches)
    params = job.get("parameters") or {}
    # Fall back to the job-level parameters when search rows are absent
    # (jobs recorded before per-search storage).
    if not primaries and params:
        primaries = [{"program": job.get("program"), "database": job.get("database"),
                      "parameters": params, "hits": job.get("hits") or []}]
    hits = job.get("hits") or []
    top = hits[0] if hits else None

    def param_lines() -> str:
        lines = []
        for s in primaries:
            p = s.get("parameters") or {}
            defaults = p.get("ncbi_defaults") or NCBI_DEFAULTS.get(s.get("program") or "", {})
            line = (f"{s.get('program')} against {s.get('database')}: E-value cutoff "
                    f"{_fmt(p.get('evalue_threshold'))}, word size {_fmt(p.get('word_size'))}, "
                    f"matrix {_fmt(p.get('matrix'))}")
            if p.get("short_query_adjusted"):
                line += " (short-query adjusted)"
            if defaults:
                line += (f"; NCBI defaults for comparison: E-value cutoff "
                         f"{_fmt(defaults.get('evalue_threshold'))}, word size "
                         f"{_fmt(defaults.get('word_size'))}, matrix {_fmt(defaults.get('matrix'))}")
            lines.append(line + ".")
        return " ".join(lines)

    if any(k in q for k in ("word size", "wordsize")):
        return f"For job {job['id']}: {param_lines()}"
    if any(k in q for k in ("matrix", "scoring", "pam", "blosum")):
        return f"For job {job['id']}: {param_lines()}"
    if any(k in q for k in ("cutoff", "cut-off", "cut off", "threshold", "parameter", "settings")):
        return f"For job {job['id']}: {param_lines()}"
    if any(k in q for k in ("compare", "comparison", "best program", "which program", "all program")):
        if len(primaries) < 2:
            return (f"Job {job['id']} ran one program ({job.get('program')}), so there is no "
                    "cross-program comparison in the stored results. " + param_lines())
        parts = []
        for s in primaries:
            t = _top(s)
            if t:
                parts.append(f"{s.get('program')}: top hit {t.get('accession', '?')} "
                             f"({_fmt(t.get('organism'))}), E-value {_fmt(t.get('evalue'))}, "
                             f"identity {_fmt(t.get('identity'))}%, coverage "
                             f"{_fmt(t.get('query_coverage'))}%, {_fmt(t.get('classification'))}")
            elif s.get("status") == "failed":
                # Quote the stored reason, so a skipped program never reads as "no matches".
                parts.append(f"{s.get('program')}: search failed ({s.get('error') or 'no reason stored'})")
            else:
                parts.append(f"{s.get('program')}: no hits stored")
        ranked = sorted((s for s in primaries if _top(s)),
                        key=lambda s: float(_top(s).get("evalue", 999.0)))
        best = (f" Lowest top-hit E-value: {ranked[0].get('program')}." if ranked else "")
        return f"For job {job['id']}: " + "; ".join(parts) + "." + best
    if any(k in q for k in ("e-value", "evalue", "significant", "confidence", "confident")):
        if not top:
            return (f"Job {job['id']} has no stored hits (status {job.get('status')}), so I can't "
                    "answer that from stored results. Send a new sequence or accession to run a search.")
        return (
            f"For job {job['id']}, the top hit {top.get('accession', '?')} has E-value "
            f"{_fmt(top.get('evalue'))}, identity {_fmt(top.get('identity'))}%, coverage "
            f"{_fmt(top.get('query_coverage'))}%, classified as {_fmt(top.get('classification'))} "
            f"(program {job.get('program', '?')} against {job.get('database', '?')}). "
            f"Stored cutoffs: strong E <= {_fmt(config.STRONG_MAX_EVALUE)} with coverage >= "
            f"{_fmt(config.STRONG_MIN_COVERAGE)}%; borderline up to E <= "
            f"{_fmt(config.BORDERLINE_MAX_EVALUE)}. Outcome: {job.get('outcome') or 'see results page'}. "
            + param_lines())
    if any(k in q for k in ("top hit", "best hit", "what did", "result", "found")):
        if not top:
            return (f"Job {job['id']} has no stored hits (status {job.get('status')}), so I can't "
                    "answer that from stored results.")
        return (
            f"Top hit for job {job['id']}: {top.get('accession', '?')} "
            f"({_fmt(top.get('organism'))}), E-value {_fmt(top.get('evalue'))}, identity "
            f"{_fmt(top.get('identity'))}%, coverage {_fmt(top.get('query_coverage'))}%, "
            f"classified as {_fmt(top.get('classification'))}.")
    if any(k in q for k in ("program", "database", "why")):
        return (
            f"Job {job['id']} used {job.get('program', '?')} against {job.get('database', '?')}. "
            f"Reason recorded: {params.get('rationale', 'see step log on the results page')}. "
            + param_lines())
    if not hits and not primaries:
        return (f"Job {job['id']} has no stored hits (status {job.get('status')}), so I can't answer "
                "that from stored results. Send a new sequence or accession to run a search.")
    if top:
        return (
            "I can't answer that from the stored results for this job. "
            f"I can quote its stored values — top hit {top.get('accession', '?')}, E-value "
            f"{_fmt(top.get('evalue'))}, identity {_fmt(top.get('identity'))}%, coverage "
            f"{_fmt(top.get('query_coverage'))}% — or run a new search if you send a sequence.")
    return ("I can't answer that from the stored results for this job. "
            "Ask about its E-value, word size, matrix, parameters, top hit, or program comparison.")
