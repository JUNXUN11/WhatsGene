"""NCBI client — superseded by app/blast_backend.py (PRD §8 interface).

Kept as a thin shim so older imports keep working; new code should use
NCBIWebBackend / FixtureBackend from app.blast_backend.
"""
from __future__ import annotations

from .blast_backend import NCBIWebBackend

_backend = NCBIWebBackend()


def fetch_by_accession(accession: str) -> dict:
    return _backend.fetch_by_accession(accession)


def submit_blast(*, sequence: str, program: str, database: str, parameters: dict) -> str:
    return _backend.submit(sequence=sequence, program=program, database=database, parameters=parameters)


def poll_blast(rid: str) -> str:
    return _backend.poll(rid)


def fetch_blast_results(rid: str) -> list[dict]:
    return _backend.fetch_results(rid)
