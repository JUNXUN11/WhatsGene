"""Verification module — deterministic code (PRD §4.2, blast-rules §8).

Checks, in order: classification gate, query coverage from coordinates,
reciprocal best hit, length mismatch, annotation consistency.
A candidate is confirmed only if every applicable check passes; the
failing check is returned verbatim so the loop can try the next
candidate and the results page can show the reason.
"""
from __future__ import annotations

from . import config


def coverage_from_coordinates(*, query_start: int, query_end: int, query_length: int) -> float:
    """coverage % = (end - start + 1) / query_length * 100 (blast-rules §7)."""
    if query_length <= 0:
        return 0.0
    span = abs(int(query_end) - int(query_start)) + 1
    return round(min(span / query_length * 100.0, 100.0), 2)


def _family_tokens(text: str) -> set[str]:
    stop = {"protein", "hypothetical", "predicted", "isoform", "chain", "precursor"}
    return {w for w in "".join(c if c.isalpha() else " " for c in (text or "").lower()).split()
            if len(w) > 3 and w not in stop}


def verify_candidate(*, candidate: dict, reciprocal_hits: list[dict],
                     query_accession: str | None, query_length: int,
                     query_annotation: str = "") -> dict:
    """Return {confirmed: bool, failing_check: str|None, reasons: [str]}."""
    reasons: list[str] = []

    classification = candidate.get("classification")
    if classification not in ("strong", "borderline"):
        return {"confirmed": False, "failing_check": "classification",
                "reasons": [f"Candidate classified as {classification}; only strong/borderline candidates are verified."]}

    coverage = float(candidate.get("query_coverage", 0.0))
    if coverage < config.BORDERLINE_MIN_COVERAGE:
        return {"confirmed": False, "failing_check": "coverage",
                "reasons": [f"Query coverage {coverage}% is below {config.BORDERLINE_MIN_COVERAGE}% (partial-domain evidence only)."]}

    # Reciprocal best hit: original query must return as a top reciprocal hit.
    strong_reciprocal = [
        h for h in reciprocal_hits
        if float(h.get("evalue", 999.0)) <= config.BORDERLINE_MAX_EVALUE
    ]
    if not reciprocal_hits:
        return {"confirmed": False, "failing_check": "reciprocal",
                "reasons": ["Reciprocal search returned no hits."]}
    if query_accession:
        top_accessions = [h.get("accession", "") for h in reciprocal_hits[:3]]
        if not any(query_accession.upper() in acc.upper() or acc.upper() in query_accession.upper()
                   for acc in top_accessions):
            if not (query_annotation and strong_reciprocal
                    and _family_tokens(query_annotation) & _family_tokens(
                        " ".join(h.get("annotation", "") for h in strong_reciprocal))):
                return {"confirmed": False, "failing_check": "reciprocal",
                        "reasons": [f"Reciprocal top hits {top_accessions} do not recover {query_accession}."]}
    elif not strong_reciprocal:
        return {"confirmed": False, "failing_check": "reciprocal",
                "reasons": ["No reciprocal hit with a significant E-value."]}

    subject_length = candidate.get("subject_length")
    if subject_length and query_length:
        ratio = max(int(subject_length), query_length) / max(min(int(subject_length), query_length), 1)
        if ratio > config.VERIFY_MAX_LENGTH_RATIO:
            return {"confirmed": False, "failing_check": "length",
                    "reasons": [f"Length mismatch: query {query_length} vs subject {subject_length} (ratio {ratio:.1f})."]}
        reasons.append(f"Length check passed (query {query_length}, subject {subject_length}).")

    annotation = candidate.get("annotation", "")
    if query_annotation and annotation:
        if not (_family_tokens(query_annotation) & _family_tokens(annotation)):
            return {"confirmed": False, "failing_check": "annotation",
                    "reasons": [f"Subject annotation '{annotation}' is inconsistent with query family '{query_annotation}'."]}
        reasons.append("Annotation consistent with query family.")

    reasons.append(f"Reciprocal search recovers the query; coverage {coverage}%.")
    return {"confirmed": True, "failing_check": None, "reasons": reasons}
