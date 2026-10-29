"""BLAST backend interface (PRD §8).

One implementation now (NCBI web); local BLAST+ is post-submission.
The agent loop depends only on this interface, so the eval harness can
inject recorded responses (fixtures) offline.

Hit dict contract (docs/blast-rules.md §7): accession, organism,
identity (%), query_start, query_end, alignment_length, subject_length,
annotation, bit_score, evalue. Coverage is computed from coordinates
in code, never taken from a hit or a model.
"""
from __future__ import annotations

from typing import Protocol


class BlastNotWired(RuntimeError):
    """Raised when a live backend operation is not wired yet."""


class BlastBackend(Protocol):
    def fetch_by_accession(self, accession: str) -> dict:
        """Return {accession, sequence, organism, annotation}."""
        ...

    def submit(self, *, sequence: str, program: str, database: str, parameters: dict) -> str:
        """Submit a search, return an RID/token."""
        ...

    def poll(self, rid: str) -> str:
        """Return 'waiting' | 'ready' | 'failed' | 'expired'."""
        ...

    def fetch_results(self, rid: str) -> list[dict]:
        """Return parsed hits for a ready RID."""
        ...


class NCBIWebBackend:
    """NCBI web implementation (E-utilities + BLAST URL API, Biopython).

    Live submit/poll/parse is not wired in this rework; every call fails
    loudly with BlastNotWired so the loop reports it instead of faking
    results. Offline behaviour is proven via FixtureBackend (tests).
    """

    def fetch_by_accession(self, accession: str) -> dict:
        raise BlastNotWired(
            f"NCBI E-utilities fetch not wired yet (accession {accession}). "
            "Paste the FASTA sequence, or run the offline eval harness."
        )

    def submit(self, *, sequence: str, program: str, database: str, parameters: dict) -> str:
        raise BlastNotWired(
            f"NCBI BLAST submission not wired yet ({program} vs {database}). "
            "Offline behaviour is covered by the fixture eval harness."
        )

    def poll(self, rid: str) -> str:
        raise BlastNotWired("NCBI BLAST polling not wired yet.")

    def fetch_results(self, rid: str) -> list[dict]:
        raise BlastNotWired("NCBI BLAST result parsing not wired yet.")


class FixtureBackend:
    """Recorded-response backend for the offline eval harness.

    primary_hits: hits returned for every primary/retry search.
    reciprocal_hits: {candidate_accession: hits} for reciprocal searches.
    Searches are distinguished by parameters['kind'] == 'reciprocal'
    plus parameters['candidate_accession'].
    """

    def __init__(self, *, sequences: dict[str, dict] | None = None,
                 primary_hits: list[dict] | None = None,
                 reciprocal_hits: dict[str, list[dict]] | None = None):
        self._sequences = sequences or {}
        self._primary = primary_hits or []
        self._reciprocal = reciprocal_hits or {}
        self.submissions: list[dict] = []
        self._counter = 0

    def fetch_by_accession(self, accession: str) -> dict:
        try:
            return dict(self._sequences[accession.upper()])
        except KeyError:
            raise BlastNotWired(f"No fixture sequence recorded for {accession}.")

    def submit(self, *, sequence: str, program: str, database: str, parameters: dict) -> str:
        self._counter += 1
        rid = f"FIXTURE-{self._counter}"
        self.submissions.append({
            "rid": rid, "program": program, "database": database,
            "parameters": dict(parameters), "sequence_len": len(sequence),
        })
        return rid

    def poll(self, rid: str) -> str:
        return "ready"

    def fetch_results(self, rid: str) -> list[dict]:
        sub = next((s for s in self.submissions if s["rid"] == rid), None)
        if sub and sub["parameters"].get("kind") == "reciprocal":
            candidate = sub["parameters"].get("candidate_accession", "")
            return [dict(h) for h in self._reciprocal.get(candidate, [])]
        return [dict(h) for h in self._primary]
