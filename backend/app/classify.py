"""Deterministic significance classification (FR6).

Thresholds from docs/blast-rules.md §6, values in app/config.py.
The model never calls this to *decide* significance — it only explains
the label this module returns.
"""
from __future__ import annotations

from . import config


def classify_hit(evalue: float, query_coverage: float,
                 cutoffs: dict | None = None) -> str:
    """Return 'strong' | 'borderline' | 'not_significant'.

    query_coverage is a percent (0–100). Default rules (blast-rules.md §7):
      strong          E <= 1e-5 and coverage >= 70%
      borderline      1e-5 < E <= 1e-2, or E <= 1e-5 with 30% <= coverage < 70%
      not_significant E > 1e-2, or coverage < 30% regardless of E

    A job may carry a custom cut-off snapshot (Settings, decision 009);
    the same shape is judged with those exact values instead.
    """
    c = cutoffs or {}
    strong_e = float(c.get("strong_max_evalue", config.STRONG_MAX_EVALUE))
    strong_cov = float(c.get("strong_min_coverage", config.STRONG_MIN_COVERAGE))
    bord_e = float(c.get("borderline_max_evalue", config.BORDERLINE_MAX_EVALUE))
    bord_cov = float(c.get("borderline_min_coverage", config.BORDERLINE_MIN_COVERAGE))
    if query_coverage < bord_cov:
        return "not_significant"
    if evalue > bord_e:
        return "not_significant"
    if evalue <= strong_e and query_coverage >= strong_cov:
        return "strong"
    return "borderline"


def classify_hits(hits: list[dict], cutoffs: dict | None = None) -> list[dict]:
    """Add a 'classification' field to each parsed hit dict in place-safe copy."""
    out: list[dict] = []
    for hit in hits:
        labelled = dict(hit)
        labelled["classification"] = classify_hit(
            float(hit.get("evalue", 999.0)),
            float(hit.get("query_coverage", 0.0)),
            cutoffs,
        )
        out.append(labelled)
    return out


_VIRAL_TERMS = ("virus", "hiv", "siv", "lentivirus", "viral")
_BACTERIAL_HINTS = ("bacteria", "bacterial", "transposase", "escherichia",
                    "salmonella", "bacillus", "staphylococcus", "pseudomonas",
                    "mycobacterium", "streptomyces", "cyanobacter", "clostridium")


def flag_unexpected_taxa(hits: list[dict], *, query_organism: str = "",
                         query_annotation: str = "") -> list[dict]:
    """Add taxa_flag='unexpected_taxa' to bacterial hits on viral queries.

    A flag only — never a rejection. Fires when the query is viral (HIV/SIV)
    and a hit looks bacterial (e.g. bacterial transposase on an HIV-1 pol
    search, Lab 04 Q4). Non-viral queries are untouched.
    """
    query_text = f"{query_organism} {query_annotation}".lower()
    if not any(term in query_text for term in _VIRAL_TERMS):
        return hits
    out = []
    for hit in hits:
        entry = dict(hit)
        hit_text = f"{entry.get('organism', '')} {entry.get('annotation', '')}".lower()
        entry["taxa_flag"] = ("unexpected_taxa"
                              if any(h in hit_text for h in _BACTERIAL_HINTS)
                              and not any(v in hit_text for v in _VIRAL_TERMS)
                              else None)
        out.append(entry)
    return out
