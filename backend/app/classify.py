"""Deterministic significance classification (FR6).

Thresholds from docs/blast-rules.md §6, values in app/config.py.
The model never calls this to *decide* significance — it only explains
the label this module returns.
"""
from __future__ import annotations

from . import config


def classify_hit(evalue: float, query_coverage: float) -> str:
    """Return 'strong' | 'borderline' | 'not_significant'.

    query_coverage is a percent (0–100).
    Rules (docs/blast-rules.md §6):
      strong          E <= 1e-5 and coverage >= 70%
      borderline      1e-5 < E <= 1e-2, or E <= 1e-5 with 30% <= coverage < 70%
      not_significant E > 1e-2, or coverage < 30% regardless of E
    """
    if query_coverage < config.BORDERLINE_MIN_COVERAGE:
        return "not_significant"
    if evalue > config.BORDERLINE_MAX_EVALUE:
        return "not_significant"
    if evalue <= config.STRONG_MAX_EVALUE and query_coverage >= config.STRONG_MIN_COVERAGE:
        return "strong"
    return "borderline"


def classify_hits(hits: list[dict]) -> list[dict]:
    """Add a 'classification' field to each parsed hit dict in place-safe copy."""
    out: list[dict] = []
    for hit in hits:
        labelled = dict(hit)
        labelled["classification"] = classify_hit(
            float(hit.get("evalue", 999.0)),
            float(hit.get("query_coverage", 0.0)),
        )
        out.append(labelled)
    return out
