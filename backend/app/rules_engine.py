"""Rules engine: intent + detected input type -> program/database.

Deterministic mapping from docs/blast-rules.md §1 (PRD §3). The model
never chooses the program directly; it may only propose a deviation
(logged, original preserved — see agent loop).
"""
from __future__ import annotations


def choose_search(*, intent: dict, detected_type: str) -> dict:
    """Return {program, database, organism_filter, reason, rule}.

    organism_filter is the intent's target organism/group (or None).
    """
    target = intent.get("target_organism")
    goal = intent.get("goal", "find_related_gene")
    raw_q = (intent.get("raw_question") or "").lower()
    wants_gene_discovery = "gene" in raw_q

    if detected_type == "protein" and goal == "find_related_gene" and target and wants_gene_discovery:
        return {
            "program": "tblastn",
            "database": "est",
            "organism_filter": target,
            "reason": (
                f"Protein query looking for a related gene in {target}: search the "
                "protein against DNA/EST sequences (tblastn, Find-a-Gene pattern)."
            ),
            "rule": "blast-rules §1: protein + find-in-target-group -> tblastn/est",
        }
    if detected_type == "protein":
        return {
            "program": "blastp",
            "database": "refseq_protein",
            "organism_filter": target,
            "reason": "Protein query against a protein database (blastp).",
            "rule": "blast-rules §1: protein identify -> blastp/refseq_protein",
        }
    if detected_type == "dna" and goal == "find_related_gene" and target:
        return {
            "program": "blastn",
            "database": "refseq_nucleotide",
            "organism_filter": target,
            "reason": f"DNA query searched against nucleotide sequences, limited to {target} (blastn).",
            "rule": "blast-rules §1: DNA + target group -> blastn/refseq_nucleotide",
        }
    return {
        "program": "blastn",
        "database": "refseq_nucleotide",
        "organism_filter": target,
        "reason": "DNA query against a nucleotide database (blastn).",
        "rule": "blast-rules §1: DNA identify -> blastn/refseq_nucleotide",
    }
