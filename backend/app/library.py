"""File-drop library: inbox inventory, confirmed sorting, custom databases.

Users drop messy files into one inbox folder. Deterministic code reads
each file and proposes what it is (query, database source, document,
result, unknown); the user confirms in the Library page; only then does
sorting copy files into the library, never moving or deleting the
original. Sorted FASTA files become one-click searches or sources for
small custom BLAST databases built locally with makeblastdb.

The same functions back the MCP tools in app/mcp_server.py, so a model
can propose the same sorting through MCP while code validates, copies,
builds, and searches. Nothing here calls a model.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config
from .search_backend import (SearchError, local_seqids_for_organism,
                             register_custom_database, resolve_blast_db_dir)
from .validate import ValidationError, detect_type, looks_like_accession

CATEGORIES = ("query", "database_source", "document", "result", "unknown")
_FASTA_SUFFIXES = {".fa", ".fasta", ".faa", ".fna", ".fas", ".fsa"}
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,39}$")
_RESERVED_NAMES = {"swissprot", "nr", "nt", "est", "refseq_protein",
                   "refseq_nucleotide", "pdbaa", "custom_databases"}


class LibraryError(RuntimeError):
    """Raised when a library operation cannot proceed."""


def inbox_dir() -> Path:
    path = Path(config.INBOX_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def library_dir() -> Path:
    path = Path(config.LIBRARY_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def validate_database_name(name: str) -> str:
    """A custom database name: lowercase slug, not a built-in name."""
    cleaned = (name or "").strip().lower()
    if not _NAME_RE.match(cleaned):
        raise ValueError(
            "Database name must start with a letter and use 3-40 lowercase "
            "letters, digits, or underscores (e.g. worm_globins).")
    if cleaned in _RESERVED_NAMES:
        raise ValueError(f"{cleaned} is a built-in database name. Choose another name.")
    return cleaned


def suggest_database_name(filename: str) -> str:
    stem = Path(filename).name
    for suffix in (".gz", ".fa", ".fasta", ".faa", ".fna", ".fas", ".fsa", ".txt"):
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
    slug = re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")
    if slug and slug[0].isdigit():
        slug = "db_" + slug
    slug = (slug or "custom_db")[:40].rstrip("_")
    if len(slug) < 3:
        slug = slug + "_db"
    try:
        return validate_database_name(slug)
    except ValueError:
        return "custom_db"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_within(root: Path, rel: str) -> Path:
    """Resolve a user-supplied relative path inside root, or raise."""
    candidate = (Path(root) / (rel or "")).resolve()
    base = Path(root).resolve()
    if candidate != base and base not in candidate.parents:
        raise ValueError("Path escapes its folder. Use a file inside the folder.")
    return candidate


def _read_sample(path: Path, limit: int = 4_000_000) -> tuple[str, bool]:
    """First bytes of a (maybe gzipped) file as text; (text, is_binary)."""
    import gzip

    try:
        if path.suffix.lower() == ".gz":
            with gzip.open(path, "rb") as handle:
                raw = handle.read(limit)
        else:
            with path.open("rb") as handle:
                raw = handle.read(limit)
    except OSError as exc:
        raise LibraryError(f"Cannot read {path.name}: {exc}") from exc
    if b"\x00" in raw:
        return "", True
    return raw.decode("utf-8", errors="replace"), False


def parse_fasta(text: str) -> dict[str, Any]:
    """Parse FASTA text: count, first record, sampled total length."""
    count = 0
    total = 0
    first_header = ""
    first_sequence = ""
    current: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(">"):
            if count == 0 and current:
                first_sequence = "".join(current)
            count += 1
            if count == 1:
                first_header = line[1:].strip()
            current = []
            continue
        if line:
            current.append(line.upper())
            total += len(line)
    if count and not first_sequence and current:
        first_sequence = "".join(current)
    return {"count": count, "total_length": total,
            "first_header": first_header, "first_sequence": first_sequence}


def _sequence_type(sequence: str) -> str | None:
    try:
        return detect_type(sequence)
    except ValidationError:
        return None


def classify_file(path: Path, root: Path) -> dict[str, Any]:
    """Inventory one file. Pure classification in code; no model call."""
    rel = str(path.relative_to(root))
    item: dict[str, Any] = {
        "root": "inbox", "path": rel, "name": path.name,
        "size_bytes": path.stat().st_size, "kind": "unknown",
        "category_proposed": "unknown", "category": None,
        "reason": "Unrecognised file; needs a human decision.",
        "confidence": "low", "sequence_type": None, "sequence_count": 0,
        "first_header": "", "total_length": 0,
        "can_search": False, "can_build_database": False, "needs_review": True,
    }
    text, is_binary = _read_sample(path)
    if is_binary or not text.strip():
        item["reason"] = "Binary or empty file; WhatsGene cannot read it as text."
        return item
    fasta = parse_fasta(text)
    if fasta["count"]:
        seq_type = _sequence_type(fasta["first_sequence"])
        item.update({
            "kind": "fasta", "sequence_count": fasta["count"],
            "first_header": fasta["first_header"],
            "total_length": fasta["total_length"],
            "sequence_type": seq_type,
            "can_search": bool(fasta["first_sequence"]),
            "can_build_database": True,
        })
        if fasta["count"] <= 5:
            item["category_proposed"] = "query"
            item["confidence"] = "high"
            item["reason"] = (f"FASTA with {fasta['count']} sequence(s); "
                              "small files are usually search queries.")
            item["needs_review"] = False
        elif fasta["count"] >= 50:
            item["category_proposed"] = "database_source"
            item["confidence"] = "high"
            item["reason"] = (f"FASTA with {fasta['count']} sequences; "
                              "large files are usually database sources.")
            item["needs_review"] = False
        else:
            item["category_proposed"] = "database_source"
            item["confidence"] = "medium"
            item["reason"] = (f"FASTA with {fasta['count']} sequences; "
                              "could be a small database or a batch of queries.")
        return item
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines and all(looks_like_accession(ln) for ln in lines[:200]):
        item.update({"kind": "accession_list", "category_proposed": "query",
                     "confidence": "high", "can_search": True,
                     "needs_review": False,
                     "reason": "Every line is an accession; a query list."})
        return item
    if len(lines) == 1 and len(lines[0]) >= 10 and _sequence_type(lines[0]):
        item.update({"kind": "raw_sequence", "category_proposed": "query",
                     "confidence": "high", "can_search": True,
                     "needs_review": False,
                     "sequence_type": _sequence_type(lines[0]),
                     "sequence_count": 1, "total_length": len(lines[0]),
                     "reason": "One raw sequence with no header; a query."})
        return item
    if path.suffix.lower() == ".json":
        try:
            payload = json.loads(text)
        except ValueError:
            payload = None
        if isinstance(payload, dict) and ("hits" in payload or "searches" in payload):
            item.update({"kind": "result", "category_proposed": "result",
                         "confidence": "high", "needs_review": False,
                         "reason": "JSON carrying hits/searches; a stored result."})
            return item
    item.update({"kind": "document", "category_proposed": "document",
                 "confidence": "medium", "needs_review": False,
                 "reason": "Readable text that is not a sequence; kept as a document."})
    return item


def inventory(root: Path | None = None) -> list[dict[str, Any]]:
    """Classify every file dropped in the inbox (sorted by path)."""
    base = Path(root) if root else inbox_dir()
    base.mkdir(parents=True, exist_ok=True)
    items = []
    for path in sorted(base.rglob("*")):
        if path.is_file() and not path.name.startswith("."):
            items.append(classify_file(path, base))
    return items


def _manifest_path(base: Path) -> Path:
    return base / "manifest.json"


def _load_manifest(base: Path) -> list[dict[str, Any]]:
    path = _manifest_path(base)
    if not path.is_file():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    return rows if isinstance(rows, list) else []


def sort_files(items: list[dict[str, Any]], *, inbox: Path | None = None,
               library_dir: Path | None = None) -> dict[str, Any]:
    """Copy confirmed files into library/<category>/. Never moves."""
    src_root = Path(inbox) if inbox else inbox_dir()
    dest_root = Path(library_dir) if library_dir else globals()["library_dir"]()
    sorted_out = []
    manifest = _load_manifest(dest_root)
    by_dest = {row.get("dest"): row for row in manifest}
    for item in items or []:
        category = str(item.get("category") or "")
        if category not in CATEGORIES:
            raise ValueError(f"Unknown sort category {category!r}. "
                             f"Choose one of: {', '.join(CATEGORIES)}.")
        source = resolve_within(src_root, str(item.get("path") or ""))
        if not source.is_file():
            raise ValueError(f"File {item.get('path')!r} is not in the inbox.")
        digest = _sha256(source)
        dest_dir = dest_root / category
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / source.name
        duplicate = False
        if dest.exists():
            if _sha256(dest) == digest:
                duplicate = True
            else:
                dest = dest_dir / f"{source.stem}__{digest[:8]}{source.suffix}"
                duplicate = dest.exists() and _sha256(dest) == digest
        if not duplicate:
            shutil.copy2(source, dest)
        rel_dest = str(dest.relative_to(dest_root))
        row = {"source_name": source.name, "original_path": str(item.get("path")),
               "dest": rel_dest, "category": category, "sha256": digest,
               "size_bytes": source.stat().st_size,
               "sorted_at": datetime.now(timezone.utc).isoformat()}
        by_dest[rel_dest] = row
        sorted_out.append({**row, "duplicate": duplicate})
    dest_root.mkdir(parents=True, exist_ok=True)
    _manifest_path(dest_root).write_text(
        json.dumps(sorted(by_dest.values(), key=lambda r: r["dest"]), indent=1),
        encoding="utf-8")
    return {"sorted": sorted_out, "library_dir": str(dest_root)}


def library_inventory(root: Path | None = None) -> list[dict[str, Any]]:
    """Files already sorted into the library, with their category."""
    base = Path(root) if root else library_dir()
    if not base.is_dir():
        return []
    manifest = {row.get("dest"): row for row in _load_manifest(base)}
    items = []
    for category in CATEGORIES:
        folder = base / category
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            rel = str(path.relative_to(base))
            item = classify_file(path, base)
            item.update({"root": "library", "path": rel,
                         "category": category,
                         "category_proposed": category,
                         "manifest": manifest.get(rel)})
            items.append(item)
    return items


def read_query_text(path: Path) -> str:
    """First searchable record from a file: FASTA record, accession, raw."""
    text, is_binary = _read_sample(path, limit=2_000_000)
    if is_binary or not text.strip():
        raise ValueError(f"{path.name} has no readable sequence.")
    fasta = parse_fasta(text)
    if fasta["count"]:
        header = fasta["first_header"] or "query"
        return f">{header}\n{fasta['first_sequence']}"
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines and looks_like_accession(lines[0]):
        return lines[0]
    if len(lines) == 1:
        return lines[0]
    raise ValueError(f"{path.name} is not a sequence file. Sort a FASTA or accession file as a query first.")


def _run_makeblastdb(fasta_path: Path, *, dbtype: str, name: str, db_dir: Path) -> int:
    """Run makeblastdb and verify with blastdbcmd. Returns seq count."""
    if not shutil.which("makeblastdb"):
        raise LibraryError("makeblastdb not found on PATH. Install NCBI BLAST+.")
    stem = db_dir / name
    if any(db_dir.glob(name + ".*")):
        raise LibraryError(
            f"Database files for {name} already exist in {db_dir}. "
            "Choose another name; WhatsGene never overwrites a database.")
    proc = subprocess.run(
        ["makeblastdb", "-in", str(fasta_path), "-dbtype", dbtype,
         "-parse_seqids", "-title", name, "-out", str(stem)],
        capture_output=True, text=True, timeout=config.LOCAL_BLAST_TIMEOUT_SECONDS)
    if proc.returncode != 0:
        for partial in db_dir.glob(name + ".*"):
            partial.unlink(missing_ok=True)
        raise LibraryError(f"makeblastdb failed for {name}: "
                           f"{(proc.stderr or proc.stdout).strip()[-400:]}")
    info = subprocess.run(["blastdbcmd", "-db", str(stem), "-info"],
                          capture_output=True, text=True, timeout=120)
    match = re.search(r"([\d,]+)\s+sequences", info.stdout or "")
    if info.returncode != 0 or not match:
        raise LibraryError(f"Built database {name} failed verification (blastdbcmd -info).")
    return int(match.group(1).replace(",", ""))


def _plain_fasta(source: Path, tmp: Path) -> Path:
    """Materialise a (maybe gzipped) FASTA source as a plain file in tmp."""
    import gzip

    if source.suffix.lower() != ".gz":
        return source
    plain = tmp / "source.fasta"
    with gzip.open(source, "rb") as src, plain.open("wb") as out:
        shutil.copyfileobj(src, out)
    return plain


def build_custom_database(source: Path, name: str,
                          db_dir: Path | None = None) -> dict[str, Any]:
    """Build a small local BLAST database from one sorted FASTA file."""
    cleaned = validate_database_name(name)
    root = Path(db_dir) if db_dir else resolve_blast_db_dir()
    if not source.is_file():
        raise LibraryError(f"Source file {source} does not exist.")
    text, is_binary = _read_sample(source)
    fasta = parse_fasta(text) if not is_binary else {"count": 0, "first_sequence": ""}
    if not fasta["count"] or not fasta["first_sequence"]:
        raise LibraryError(f"{source.name} has no FASTA sequences to build from.")
    seq_type = _sequence_type(fasta["first_sequence"])
    if seq_type is None:
        raise LibraryError(f"{source.name}: cannot tell DNA from protein in the first sequence.")
    with tempfile.TemporaryDirectory(prefix="whatsgene_db_") as tmp:
        count = _run_makeblastdb(_plain_fasta(source, Path(tmp)),
                                 dbtype="prot" if seq_type == "protein" else "nucl",
                                 name=cleaned, db_dir=root)
    entry = register_custom_database({
        "name": cleaned, "stem": cleaned,
        "dbtype": "protein" if seq_type == "protein" else "nucleotide",
        "label": f"Custom — {source.name}",
        "description": f"Built locally from {source.name} on this machine.",
        "source": source.name,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "sequence_count": count,
    }, db_dir=root)
    return {**entry, "ready": True, "sequence_count": count}


def build_database_from_taxon(organism: str, name: str,
                              db_dir: Path | None = None) -> dict[str, Any]:
    """Build a small protein database: one taxon's SwissProt subset."""
    cleaned = validate_database_name(name)
    root = Path(db_dir) if db_dir else resolve_blast_db_dir()
    if not shutil.which("blastdbcmd"):
        raise LibraryError("blastdbcmd not found on PATH. Install NCBI BLAST+.")
    try:
        seqids = local_seqids_for_organism(organism, root)
    except SearchError as exc:
        raise LibraryError(str(exc)) from exc
    with tempfile.TemporaryDirectory(prefix="whatsgene_taxon_") as tmp:
        tmp_path = Path(tmp)
        list_file = tmp_path / "seqids.txt"
        list_file.write_text("\n".join(seqids) + "\n", encoding="utf-8")
        fasta_path = tmp_path / "subset.fasta"
        with fasta_path.open("w", encoding="utf-8") as out:
            proc = subprocess.run(
                ["blastdbcmd", "-db", str(root / "swissprot"),
                 "-entry_batch", str(list_file), "-outfmt", "%f"],
                stdout=out, stderr=subprocess.PIPE, text=True,
                timeout=config.LOCAL_BLAST_TIMEOUT_SECONDS)
        if proc.returncode != 0 or not fasta_path.stat().st_size:
            raise LibraryError(
                f"Could not extract {organism} sequences from the local "
                f"swissprot copy: {(proc.stderr or '').strip()[-300:]}")
        count = _run_makeblastdb(fasta_path, dbtype="prot", name=cleaned, db_dir=root)
    entry = register_custom_database({
        "name": cleaned, "stem": cleaned, "dbtype": "protein",
        "label": f"Custom — {organism} (SwissProt subset)",
        "description": f"SwissProt sequences for {organism}, built locally; "
                       "a small database instead of the full copy.",
        "source": f"swissprot subset: {organism}",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "sequence_count": count,
    }, db_dir=root)
    return {**entry, "ready": True, "sequence_count": count}


def explain_file(item: dict[str, Any]) -> str:
    """Plain-language explanation of one inventory item (deterministic)."""
    bits = [f"{item.get('name')}: proposed as {item.get('category_proposed')} "
            f"({item.get('confidence')} confidence). {item.get('reason')}"]
    if item.get("sequence_count"):
        bits.append(f"{item['sequence_count']} sequence(s), "
                    f"type {item.get('sequence_type') or 'unknown'}, "
                    f"{item.get('total_length')} residues sampled.")
    if item.get("can_search"):
        bits.append("It can be used as a search query.")
    if item.get("can_build_database"):
        bits.append("It can be built into a small custom database.")
    if item.get("needs_review"):
        bits.append("Check this one before sorting; the proposal is uncertain.")
    return " ".join(bits)
