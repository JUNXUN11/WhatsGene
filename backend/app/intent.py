"""Structured intent from free text (PRD §3).

The model interprets; code computes. This module defines the intent
contract {goal, target_organism, unclear[]} and a deterministic fallback
parser used offline and whenever the Muse endpoint is not configured.
A live Muse call, when configured, must return this same shape; it
never chooses the BLAST program (that is the rules engine's job).
"""
from __future__ import annotations

import re

# Known target phrases -> canonical organism/group. Extend in code, not prompts.
_TARGETS: list[tuple[tuple[str, ...], str]] = [
    (("nematode", "nematodes", "worm"), "nematodes"),
    (("c. elegans", "caenorhabditis"), "C. elegans"),
    (("human", "homo sapiens"), "human"),
    (("mouse", "mus musculus"), "mouse"),
    (("e. coli", "escherichia"), "E. coli"),
    (("yeast", "saccharomyces"), "yeast"),
]


def parse_intent(question: str) -> dict:
    """Deterministic fallback intent parser. Returns the intent contract."""
    q = (question or "").strip()
    low = q.lower()

    target: str | None = None
    for keys, canonical in _TARGETS:
        if any(k in low for k in keys):
            target = canonical
            break
    if target is None:
        match = re.search(r"\bin\s+([a-z][a-z .]{2,40}?)(?:[?.!,]|$)", low)
        if match:
            phrase = match.group(1).strip()
            if phrase and phrase not in ("this", "the database"):
                target = phrase

    # Organism exclusion, e.g. "excluding HIV-1", "NOT hiv-1[organism]".
    exclude: str | None = None
    excl_match = re.search(r"(?:exclud\w+|not)\s+([a-z0-9][a-z0-9 .\-]*?)(?:\[organism\]|[?.!,]|$)", low)
    if excl_match:
        phrase = excl_match.group(1).strip()
        _EXCL_CANON = {"hiv-1": "Human immunodeficiency virus 1",
                       "hiv-2": "Human immunodeficiency virus 2",
                       "siv": "Simian immunodeficiency virus"}
        exclude = _EXCL_CANON.get(phrase, phrase or None)

    if any(k in low for k in ("what is this", "identify", "what gene", "which gene")):
        goal = "identify_sequence"
    else:
        goal = "find_related_gene"

    unclear: list[str] = []
    if goal == "find_related_gene" and target is None:
        unclear.append("target organism or group not specified")
    if not q:
        unclear.append("no question provided")

    return {"goal": goal, "target_organism": target, "exclude_organism": exclude,
            "unclear": unclear, "raw_question": q}
