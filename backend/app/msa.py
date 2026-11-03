"""Tier 2 MSA -> tree (Lab 06 + Lab 07 methods, PRD §5.1).

Collect confirmed homologs, align with MAFFT (Lab 06's tool: on this
machine when installed, else at EBI), then build a neighbor-joining tree with Poisson-corrected distances
after complete deletion of gap columns (Lab 07's MEGA preferences).
Bootstrapping and Tajima's test stay roadmap-only (owner charter).
Alignment/tree computation is deterministic code; the model only words
summaries elsewhere and never touches these numbers.
"""
from __future__ import annotations

import math
from typing import Protocol


class MsaError(RuntimeError):
    """Raised when an alignment step cannot proceed."""


class MsaBackend(Protocol):
    name: str

    def align(self, sequences: list[dict]) -> str:
        """Return aligned FASTA text for [{label, sequence}]."""
        ...


def collect_homologs(*, job: dict, searches: list[dict], backend,
                     max_sequences: int = 10) -> list[dict]:
    """Query + top strong/borderline hits, full sequences where fetchable.

    Lab 06 collects a group of about ten proteins for alignment. A hit
    whose full sequence cannot be fetched contributes its aligned
    subject sequence, with the source recorded per sequence.
    """
    out: list[dict] = []
    query_seq = (job.get("sequence") or "").strip()
    if query_seq:
        out.append({"label": job.get("accession") or "query",
                    "accession": job.get("accession") or "query",
                    "organism": "", "sequence": query_seq, "source": "query"})
    seen = {out[0]["accession"]} if out else set()
    for search in searches:
        if search.get("kind") not in ("primary", "retry"):
            continue
        for hit in search.get("hits") or []:
            if len(out) >= max_sequences:
                return out
            if hit.get("classification") not in ("strong", "borderline"):
                continue
            accession = hit.get("accession") or ""
            if not accession or accession in seen:
                continue
            seen.add(accession)
            try:
                record = backend.fetch_by_accession(accession)
                sequence, source = (record.get("sequence") or ""), "fetch_by_accession"
            except Exception:
                sequence, source = (hit.get("sequence") or ""), "hit_alignment_sequence"
            if sequence:
                out.append({"label": accession, "accession": accession,
                            "organism": hit.get("organism", ""),
                            "sequence": sequence.replace("-", ""), "source": source})
    return out


def parse_fasta(text: str) -> list[dict]:
    records: list[dict] = []
    label, chunks = None, []
    for line in (text or "").splitlines():
        line = line.strip()
        if line.startswith(">"):
            if label is not None:
                records.append({"label": label, "sequence": "".join(chunks)})
            label, chunks = line[1:].split()[0], []
        elif line:
            chunks.append(line)
    if label is not None:
        records.append({"label": label, "sequence": "".join(chunks)})
    return records


def complete_deletion(records: list[dict]) -> list[dict]:
    """Drop every column containing a gap in any sequence (Lab 07)."""
    if not records:
        return []
    width = max(len(r["sequence"]) for r in records)
    padded = [r["sequence"].ljust(width, "-") for r in records]
    keep = [i for i in range(width) if all(seq[i] != "-" for seq in padded)]
    return [{"label": r["label"], "sequence": "".join(padded[n][i] for i in keep)}
            for n, r in enumerate(records)]


def poisson_distance(seq_a: str, seq_b: str) -> float:
    """Poisson-corrected distance d = -ln(1 - p) (Lab 07 model)."""
    pairs = [(a, b) for a, b in zip(seq_a, seq_b) if a != "-" and b != "-"]
    if not pairs:
        return 0.0
    p = sum(1 for a, b in pairs if a != b) / len(pairs)
    if p >= 1.0:
        return 99.0
    return -math.log(1.0 - p)


def build_tree_newick(records: list[dict]) -> str:
    """Neighbor-joining tree (Biopython) over Poisson distances."""
    from Bio.Phylo.TreeConstruction import DistanceMatrix, DistanceTreeConstructor

    cleaned = complete_deletion(records)
    if len(cleaned) < 3:
        raise MsaError("A tree needs at least 3 aligned sequences after complete deletion.")
    names = [r["label"] for r in cleaned]
    matrix = []
    for i, rec in enumerate(cleaned):
        row = [round(poisson_distance(cleaned[j]["sequence"], rec["sequence"]), 6)
               for j in range(i + 1)]
        matrix.append(row)
    tree = DistanceTreeConstructor().nj(DistanceMatrix(names=names, matrix=matrix))
    from io import StringIO

    from Bio import Phylo

    handle = StringIO()
    Phylo.write(tree, handle, "newick")
    return handle.getvalue().strip()


# --- EBI MAFFT backend (Lab 06 tool, via REST) ---

_EBI_BASE = "https://www.ebi.ac.uk/Tools/services/rest/mafft"


def ebi_result_types(status_text: str) -> bool:
    return status_text.strip().upper() in ("FINISHED", "RUNNING", "QUEUED", "NOT_FOUND", "ERROR", "FAILURE")


class EbiMafft:
    """MAFFT at EBI over REST: submit -> poll -> aligned FASTA."""

    name = "ebi-mafft"

    def __init__(self, email: str, *, poll_seconds: float = 10.0, max_wait_seconds: float = 600.0) -> None:
        if not email:
            raise MsaError("EBI MAFFT needs a contact email (set NCBI_EMAIL in backend/.env).")
        self._email = email
        self._poll = poll_seconds
        self._max_wait = max_wait_seconds

    def align(self, sequences: list[dict]) -> str:
        import time

        import httpx

        fasta = "".join(f">{s['label']}\n{s['sequence']}\n" for s in sequences)
        with httpx.Client(timeout=60.0) as client:
            run = client.post(f"{_EBI_BASE}/run", data={
                "email": self._email, "title": "WhatsGene homologs", "sequence": fasta})
            run.raise_for_status()
            job_id = run.text.strip()
            started = time.monotonic()
            while True:
                status = client.get(f"{_EBI_BASE}/status/{job_id}")
                status.raise_for_status()
                state = status.text.strip().upper()
                if state == "FINISHED":
                    break
                if state in ("ERROR", "FAILURE", "NOT_FOUND"):
                    raise MsaError(f"EBI MAFFT job {job_id} ended as {state}.")
                if time.monotonic() - started > self._max_wait:
                    raise MsaError(f"EBI MAFFT job {job_id} did not finish in time.")
                time.sleep(self._poll)
            result = client.get(f"{_EBI_BASE}/result/{job_id}/fa")
            result.raise_for_status()
            return result.text


class LocalMafft:
    """MAFFT installed on this machine: seconds, and no sequence leaves it."""

    name = "local-mafft"

    def __init__(self, executable: str = "mafft", *, timeout_seconds: float = 600.0) -> None:
        self._exe = executable
        self._timeout = timeout_seconds

    def align(self, sequences: list[dict]) -> str:
        import subprocess
        import tempfile
        from pathlib import Path

        fasta = "".join(f">{s['label']}\n{s['sequence']}\n" for s in sequences)
        with tempfile.TemporaryDirectory(prefix="whatsgene_msa_") as tmp:
            query = Path(tmp) / "homologs.fasta"
            query.write_text(fasta, encoding="utf-8")
            try:
                proc = subprocess.run([self._exe, "--auto", "--quiet", str(query)],
                                      capture_output=True, text=True, timeout=self._timeout)
            except subprocess.TimeoutExpired as exc:
                raise MsaError(f"Local MAFFT timed out: {exc}") from exc
        if proc.returncode != 0 or not proc.stdout.strip():
            raise MsaError(f"Local MAFFT failed (exit {proc.returncode}): {proc.stderr.strip()[-300:]}")
        return proc.stdout


class FixtureMsa:
    """Recorded/padded alignment for tests and offline demos."""

    name = "fixture"

    def __init__(self, alignment: str | None = None) -> None:
        self._alignment = alignment

    def align(self, sequences: list[dict]) -> str:
        if self._alignment is not None:
            return self._alignment
        width = max(len(s["sequence"]) for s in sequences)
        return "".join(f">{s['label']}\n{s['sequence'].ljust(width, '-')}\n" for s in sequences)


def get_msa_backend() -> MsaBackend:
    from . import config

    import shutil

    if (config.SEARCH_BACKEND or "").strip().lower() == "fixture":
        return FixtureMsa()
    # Same MAFFT, run here when installed: seconds instead of the EBI
    # queue (minutes), and the homolog sequences stay on this machine.
    local = shutil.which("mafft")
    if local:
        return LocalMafft(local)
    return EbiMafft(config.NCBI_EMAIL)


def run_alignment(*, job: dict, search_backend, msa_backend: MsaBackend | None = None) -> dict:
    """Collect homologs, align, build tree, store + log on the job."""
    from . import db

    job_id = job["id"]
    msa_backend = msa_backend or get_msa_backend()
    homologs = collect_homologs(job=job, searches=db.get_searches(job_id),
                                backend=search_backend)
    if len(homologs) < 3:
        raise MsaError(
            f"Only {len(homologs)} homolog sequence(s) available; MSA needs at least 3 "
            "(query plus two confirmed hits).")
    db.add_step(job_id, step="align",
                observation=f"{len(homologs)} homologs: {', '.join(h['label'] for h in homologs)}",
                decision=f"align with {msa_backend.name}",
                reason="Confirmed homologs collected for MSA (Lab 06 group-of-ten pattern).")
    alignment = msa_backend.align(homologs)
    records = parse_fasta(alignment)
    newick = build_tree_newick(records)
    db.add_step(job_id, step="tree",
                observation=f"{len(records)} aligned sequences",
                decision="neighbor-joining tree built",
                reason="Poisson-corrected distances after complete deletion of gap columns (Lab 07 preferences); no bootstrapping (roadmap only).")
    return db.update_job(job_id, msa_alignment=alignment, tree_newick=newick,
                         homologs=homologs) or job
