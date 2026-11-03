"""Input validation — deterministic code, never the model (FR2, blast-rules STEP 1).

Boilerplate scope: normalise FASTA/raw input, detect DNA vs protein,
reject malformed input with a specific error. Accession resolution via
E-utilities lands with the NCBI client (30–31 Oct).
"""
from __future__ import annotations

import re

_DNA_CHARS = set("ACGTUN")
_PROTEIN_CHARS = set("ACDEFGHIKLMNPQRSTVWY")
_ACCESSION_RE = re.compile(r"^[A-Z]{1,3}_?\d+(\.\d+)?$")
# UniProt's published accession format (P0DTC2, A0A023GPI8). Every form
# has digits, so a raw sequence (letters only) can never match it.
_UNIPROT_RE = re.compile(
    r"^(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})(\.\d+)?$")


class ValidationError(ValueError):
    """Raised with a user-facing, specific message."""


def looks_like_accession(text: str) -> bool:
    candidate = text.strip().upper()
    return bool(_ACCESSION_RE.match(candidate) or _UNIPROT_RE.match(candidate))


_SUBRANGE_RE = re.compile(r"^([A-Z]{1,3}_?\d+(?:\.\d+)?):(\d+)-(\d+)$")


def parse_accession_query(raw: str) -> tuple[str, tuple[int, int] | None]:
    """Split 'NM_006744.4:84-689' into (accession, (start, end) 1-based incl.).

    Plain accessions return (accession, None). Anything else returns the
    input unchanged with None, so callers fall back to sequence handling.
    """
    text = (raw or "").strip().upper()
    match = _SUBRANGE_RE.match(text)
    if match:
        return match.group(1), (int(match.group(2)), int(match.group(3)))
    if looks_like_accession(text):
        return text, None
    return (raw or "").strip(), None


def normalise_sequence(raw: str) -> tuple[str, str | None]:
    """Return (sequence, fasta_header_or_None). Raises ValidationError."""
    text = (raw or "").strip()
    if not text:
        raise ValidationError("Input is empty. Paste a FASTA sequence or an NCBI accession (e.g. NP_000509).")
    header: str | None = None
    lines: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(">"):
            if header is not None:
                raise ValidationError("Multiple FASTA headers found. Submit one sequence at a time.")
            header = line[1:].strip()
            continue
        if line.startswith(";"):
            continue
        lines.append(line)
    sequence = "".join(lines).upper().replace(" ", "").replace("\r", "")
    if header is not None and not sequence:
        raise ValidationError("FASTA header found but no sequence. Paste the sequence lines after the '>' header.")
    if not sequence:
        raise ValidationError("No sequence found. Paste a FASTA sequence or an NCBI accession (e.g. NP_000509).")
    return sequence, header


def detect_type(sequence: str) -> str:
    """Return 'dna' or 'protein'. Raises ValidationError on bad alphabet."""
    seq = sequence.upper()
    bad = sorted(set(seq) - _DNA_CHARS - _PROTEIN_CHARS - {"-", "*", "X", "B", "Z", "J"})
    if bad:
        raise ValidationError(
            f"Sequence contains unsupported character(s): {', '.join(bad)}. "
            "DNA uses A/C/G/T; protein uses the 20 standard amino-acid letters."
        )
    if len(seq) < 10:
        raise ValidationError(
            f"Sequence is too short ({len(seq)} residues) to search meaningfully. "
            "Paste a longer sequence or use an accession."
        )
    dna_like = sum(1 for c in seq if c in _DNA_CHARS) / max(len(seq), 1)
    return "dna" if dna_like >= 0.9 and set(seq) <= (_DNA_CHARS | {"N", "X"}) else "protein"
