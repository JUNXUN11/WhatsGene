"""BLAST search parameters — deterministic code (blast-rules §4).

Short-query profile is traceable to reference/Lab 04.pdf Q1: the 12-aa
query PNLHGLFGRKTG gets NCBI's short-query adjustment — E-value cutoff
200,000, word size 2, matrix PAM30 — versus the BLASTP defaults
(E=10, word size 3, BLOSUM62). Thresholds live here/config only,
never in model prompts.
"""
from __future__ import annotations

# NCBI reference defaults shown to users for comparison (Lab 04 Q1).
NCBI_DEFAULTS: dict[str, dict] = {
    "blastp": {"evalue_threshold": 10.0, "word_size": 3, "matrix": "BLOSUM62"},
    "blastx": {"evalue_threshold": 10.0, "word_size": 3, "matrix": "BLOSUM62"},
    "tblastn": {"evalue_threshold": 10.0, "word_size": 3, "matrix": "BLOSUM62"},
    "tblastx": {"evalue_threshold": 10.0, "word_size": 3, "matrix": "BLOSUM62"},
    "blastn": {"evalue_threshold": 10.0, "word_size": 11, "matrix": None},
}

# Protein queries at or below this length use the short-query profile.
SHORT_PROTEIN_MAX_LENGTH = 30


def is_short_query(*, detected_type: str, query_length: int) -> bool:
    return detected_type == "protein" and 0 < query_length <= SHORT_PROTEIN_MAX_LENGTH


def parameters_for(*, program: str, detected_type: str, query_length: int,
                   organism_filter: str | None = None,
                   exclude_organism: str | None = None) -> dict:
    """Return the exact parameters submitted for one search."""
    short = program == "blastp" and is_short_query(
        detected_type=detected_type, query_length=query_length)
    if short:
        params: dict = {"evalue_threshold": 200000.0, "word_size": 2, "matrix": "PAM30"}
    elif program == "blastn":
        params = {"evalue_threshold": 0.01, "word_size": 11, "matrix": None}
    else:
        params = {"evalue_threshold": 0.01, "word_size": 3, "matrix": "BLOSUM62"}
    params.update({
        "program": program,
        "organism_filter": organism_filter,
        "exclude_organism": exclude_organism,
        "filtering": "default",
        "max_target_sequences": 500,
        "short_query_adjusted": short,
        "ncbi_defaults": NCBI_DEFAULTS.get(program),
    })
    if short:
        params["short_query_reason"] = (
            f"Short protein query ({query_length} aa <= {SHORT_PROTEIN_MAX_LENGTH}): "
            "NCBI short-query adjustment (Lab 04 Q1) — a short query cannot reach "
            "a high alignment score, so the E-value cutoff is raised and a "
            "stringent matrix (PAM30) with word size 2 is used."
        )
    return params
