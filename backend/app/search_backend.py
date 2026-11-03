"""Search backend interface — LocalBlast (default), NcbiRemote (opt-in), Fixture (tests/demo).

The agent loop depends only on the SearchBackend protocol, so tests and
demos can run fully offline through Fixture while production defaults to
a local BLAST+ run. Select with SEARCH_BACKEND in backend/.env.

Hit dict contract (docs/blast-rules.md §7): accession, organism,
identity (%), query_start, query_end, alignment_length, subject_length,
annotation, bit_score, evalue, sequence. Coverage is computed from
coordinates in code, never taken from a hit or a model.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol


class SearchError(RuntimeError):
    """Raised when a search backend operation cannot proceed."""


class SearchBackend(Protocol):
    name: str

    def fetch_by_accession(self, accession: str) -> dict:
        """Return {accession, sequence, organism, annotation}."""
        ...

    def submit(self, *, sequence: str, program: str, database: str, parameters: dict) -> str:
        """Submit a search, return a token (RID for NCBI)."""
        ...

    def poll(self, token: str) -> str:
        """Return 'waiting' | 'ready' | 'failed' | 'expired'."""
        ...

    def fetch_results(self, token: str) -> list[dict]:
        """Return parsed hits for a ready token."""
        ...


def parse_blast_xml(xml_text: str) -> list[dict]:
    """Parse BLAST XML (local -outfmt 5 or NCBI) into hit dicts. Pure."""
    import io
    import re

    from Bio.Blast import NCBIXML

    hits: list[dict] = []
    for record in NCBIXML.parse(io.StringIO(xml_text)):
        for alignment in record.alignments:
            if not alignment.hsps:
                continue
            hsp = alignment.hsps[0]
            align_len = max(hsp.align_length, 1)
            title = alignment.title or ""
            organism_match = re.search(r"\[([^\]]+)\]\s*$", title)
            organism = organism_match.group(1) if organism_match else ""
            if not organism:  # SwissProt-style deflines carry OS= instead
                os_match = re.search(r"OS=([^=]+?)(?:\s+[A-Z]{2}=|$)", title)
                organism = os_match.group(1).strip() if os_match else ""
            hits.append({
                "accession": alignment.accession,
                "organism": organism,
                "annotation": (alignment.hit_def or alignment.title or "").strip(),
                "identity": round(hsp.identities / align_len * 100.0, 2),
                "query_start": hsp.query_start,
                "query_end": hsp.query_end,
                "alignment_length": hsp.align_length,
                "subject_length": alignment.length,
                "bit_score": round(float(hsp.bits), 2),
                "evalue": float(hsp.expect),
                "sequence": (hsp.sbjct or "").replace("-", ""),
            })
    return hits


# --- LocalBlast pure helpers (unit-tested; no subprocess here) ---

_LOCAL_PROGRAMS = ("blastp", "blastn")
# Rules-engine protein databases served by the local swissprot copy.
# The step log and job parameters always record backend=local so the
# results page never claims a search ran on the named remote database.
# Extra entries are NCBI-sourced databases built locally with makeblastdb
# from FASTA (NCBI prebuilt files do not open on arm64; decision 002):
# pdbaa + RefSeq viral protein (blastp), 16S rRNA + fungi ITS +
# mitochondrion + viral genomes (blastn). Files live as <stem>.* in $BLASTDB.
_LOCAL_DB_MAP = {
    "swissprot": "swissprot", "refseq_protein": "swissprot", "nr": "swissprot",
    "pdbaa": "pdbaa", "pdb_protein": "pdbaa",
    "refseq_viral_protein": "refseq_viral_protein",
    "viral_protein": "refseq_viral_protein",
    "16s_rrna": "16s_rrna", "16S_ribosomal_RNA": "16s_rrna",
    "fungi_its": "fungi_its", "ITS_RefSeq_Fungi": "fungi_its",
    "mito_genomic": "mito_genomic", "mito": "mito_genomic",
    "refseq_viral_genomic": "refseq_viral_genomic",
    "viral_genomic": "refseq_viral_genomic",
}
# Databases tried, in order, by fetch_by_accession (protein first).
_LOCAL_FETCH_STEMS = ("swissprot", "pdbaa", "refseq_viral_protein",
                      "16s_rrna", "fungi_its", "mito_genomic",
                      "refseq_viral_genomic")

# User-selectable local databases (canonical name -> catalog entry).
# `name` is what jobs store and the form offers; aliases in _LOCAL_DB_MAP
# resolve to the same stem but are not offered as separate choices.
LOCAL_DATABASE_CATALOG: list[dict] = [
    {"name": "swissprot", "stem": "swissprot", "dbtype": "protein",
     "label": "SwissProt — curated proteins",
     "description": "575k curated UniProt proteins. Default local copy."},
    {"name": "pdbaa", "stem": "pdbaa", "dbtype": "protein",
     "label": "PDB proteins (pdbaa)",
     "description": "Proteins with known 3D structures, from NCBI pdbaa."},
    {"name": "refseq_viral_protein", "stem": "refseq_viral_protein", "dbtype": "protein",
     "label": "RefSeq viral proteins",
     "description": "All RefSeq viral proteins, including HIV-1 pol."},
    {"name": "16s_rrna", "stem": "16s_rrna", "dbtype": "nucleotide",
     "label": "16S rRNA — bacteria and archaea",
     "description": "Type-strain 16S sequences for bacterial identification."},
    {"name": "fungi_its", "stem": "fungi_its", "dbtype": "nucleotide",
     "label": "Fungi ITS",
     "description": "Fungal internal transcribed spacer reference sequences."},
    {"name": "mito_genomic", "stem": "mito_genomic", "dbtype": "nucleotide",
     "label": "Mitochondrion genomes",
     "description": "RefSeq mitochondrial genomes across species."},
    {"name": "refseq_viral_genomic", "stem": "refseq_viral_genomic", "dbtype": "nucleotide",
     "label": "RefSeq viral genomes",
     "description": "RefSeq viral reference genomes."},
]


def _custom_registry_path(db_dir: Path) -> Path:
    return db_dir / "custom_databases.json"


def load_custom_databases(db_dir: Path | str | None = None) -> list[dict]:
    """Custom databases registered in $BLASTDB/custom_databases.json."""
    import json

    try:
        root = Path(db_dir) if db_dir else resolve_blast_db_dir()
    except SearchError:
        return []
    path = _custom_registry_path(root)
    if not path.is_file():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    out = []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and row.get("name") and row.get("stem") \
                and row.get("dbtype") in ("protein", "nucleotide"):
            out.append({**row, "custom": True})
    return out


def register_custom_database(entry: dict, db_dir: Path | str | None = None) -> dict:
    """Add or replace one custom database in the registry. Returns it."""
    import json

    root = Path(db_dir) if db_dir else resolve_blast_db_dir()
    rows = [r for r in load_custom_databases(root) if r["name"] != entry["name"]]
    rows.append({k: entry[k] for k in
                 ("name", "stem", "dbtype", "label", "description") if k in entry} |
                {k: entry[k] for k in ("source", "built_at", "sequence_count") if k in entry})
    _custom_registry_path(root).write_text(
        json.dumps(rows, indent=1), encoding="utf-8")
    return load_custom_databases(root)[-1] if rows else dict(entry)


def local_database_entry(name: str | None,
                         db_dir: Path | str | None = None) -> dict | None:
    """Catalog entry for a canonical local database name, or None."""
    wanted = (name or "").strip()
    for entry in LOCAL_DATABASE_CATALOG:
        if entry["name"] == wanted:
            return entry
    for entry in load_custom_databases(db_dir):
        if entry["name"] == wanted:
            return entry
    return None


def local_database_catalog(db_dir: Path | str | None = None) -> list[dict]:
    """Catalog with a `ready` flag from files present in $BLASTDB."""
    try:
        root = Path(db_dir) if db_dir else resolve_blast_db_dir()
    except SearchError:
        root = None
    out = []
    for entry in [*LOCAL_DATABASE_CATALOG, *load_custom_databases(root)]:
        ready = bool(root and any(root.glob(entry["stem"] + ".*")))
        out.append({**entry, "ready": ready})
    return out


def resolve_blast_db_dir() -> Path:
    """Return $BLASTDB or raise a clear SearchError. No searches run here."""
    import os

    raw = os.environ.get("BLASTDB", "").strip()
    if not raw:
        raise SearchError(
            "BLASTDB is not set. LocalBlast needs BLASTDB pointing at a directory "
            "containing a swissprot BLAST database plus names.dmp, nodes.dmp and "
            "sprot.taxidmap for organism filters, e.g. BLASTDB=/data/blastdb.")
    path = Path(raw)
    if not path.is_dir():
        raise SearchError(f"BLASTDB={raw} is not a directory.")
    return path


def build_blast_command(*, program: str, db_path: Path, query_fasta: Path,
                        evalue: float | None = None, word_size: int | None = None,
                        matrix: str | None = None,
                        seqidlist_path: Path | None = None) -> list[str]:
    """Build the BLAST+ argv. Pure; raises SearchError on bad program.

    Organism scoping uses -seqidlist (a file of seqids). -entrez_query is
    never used: BLAST+ requires -remote for it, which breaks offline runs.
    """
    if program not in _LOCAL_PROGRAMS:
        raise SearchError(
            f"LocalBlast supports {list(_LOCAL_PROGRAMS)} only, not {program!r}. "
            "Set SEARCH_BACKEND=ncbi for other programs.")
    cmd = [program, "-db", str(db_path), "-query", str(query_fasta),
           "-outfmt", "5", "-out", "-"]
    if evalue is not None:
        cmd += ["-evalue", str(evalue)]
    if word_size is not None:
        cmd += ["-word_size", str(word_size)]
    if matrix is not None:
        cmd += ["-matrix", matrix]
    if seqidlist_path is not None:
        cmd += ["-seqidlist", str(seqidlist_path)]
    return cmd


def parse_names_dmp(text: str) -> dict[str, int]:
    """Map scientific names to taxids from names.dmp content. Pure."""
    names: dict[str, int] = {}
    for line in text.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4 or parts[3] != "scientific name":
            continue
        try:
            names[parts[1]] = int(parts[0])
        except ValueError:
            continue
    return names


def parse_nodes_dmp(text: str) -> dict[int, set[int]]:
    """Map parent taxids to child taxids from nodes.dmp content. Pure."""
    children: dict[int, set[int]] = {}
    for line in text.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            continue
        try:
            taxid, parent = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        children.setdefault(parent, set()).add(taxid)
    return children


def expand_taxid(taxid: int, children: dict[int, set[int]]) -> set[int]:
    """Return a taxid plus all its descendants. Pure."""
    seen: set[int] = set()
    stack = [taxid]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(children.get(current, ()))
    return seen


def resolve_organism_taxid(organism: str, names: dict[str, int]) -> int:
    """Resolve an organism name to a taxid (exact, then case-insensitive). Pure."""
    wanted = (organism or "").strip()
    if wanted in names:
        return names[wanted]
    lowered = wanted.lower()
    for name, taxid in names.items():
        if name.lower() == lowered:
            return taxid
    raise SearchError(
        f"Organism {wanted!r} is not in the local taxonomy files. "
        "Check the spelling or run without an organism filter.")


def select_seqids(map_text: str, wanted: set[int]) -> list[str]:
    """Select seqids whose taxid is wanted from seqid<tab>taxid lines. Pure."""
    seqids: list[str] = []
    for line in map_text.splitlines():
        seqid, _, taxid = line.partition("\t")
        try:
            if int(taxid.strip()) in wanted:
                seqids.append(seqid.strip())
        except ValueError:
            continue
    return seqids


_TAXONOMY_FILES = ("names.dmp", "nodes.dmp", "sprot.taxidmap")


def local_seqids_for_organism(organism: str, db_dir: Path) -> list[str]:
    """Return local seqids for an organism (higher taxa cover descendants).

    Reads names.dmp, nodes.dmp and sprot.taxidmap from the BLAST bulk-data
    directory. Raises SearchError when files are missing, the organism is
    unknown, or no local sequence carries the organism's taxids.
    """
    missing = [name for name in _TAXONOMY_FILES if not (db_dir / name).is_file()]
    if missing:
        raise SearchError(
            f"Local taxonomy files missing in {db_dir}: {', '.join(missing)}. "
            "Stage names.dmp + nodes.dmp (NCBI taxdmp.zip) and the "
            "sprot.taxidmap used at makeblastdb time next to the database.")
    names = parse_names_dmp((db_dir / "names.dmp").read_text(encoding="utf-8"))
    taxid = resolve_organism_taxid(organism, names)
    children = parse_nodes_dmp((db_dir / "nodes.dmp").read_text(encoding="utf-8"))
    wanted = expand_taxid(taxid, children)
    seqids = select_seqids(
        (db_dir / "sprot.taxidmap").read_text(encoding="utf-8"), wanted)
    if not seqids:
        raise SearchError(
            f"No local swissprot sequence carries {organism.strip()!r} "
            f"(taxid {taxid}). The organism may be absent from this copy; "
            "set SEARCH_BACKEND=ncbi to search NCBI instead.")
    return seqids


def select_seqids_filtered(map_text: str, include_taxids: set[int] | None,
                           exclude_taxids: set[int]) -> list[str]:
    """Seqids in include_taxids (all if None) minus exclude_taxids. Pure."""
    seqids: list[str] = []
    for line in map_text.splitlines():
        seqid, _, taxid = line.partition("\t")
        try:
            tax = int(taxid.strip())
        except ValueError:
            continue
        if include_taxids is not None and tax not in include_taxids:
            continue
        if tax in exclude_taxids:
            continue
        seqids.append(seqid.strip())
    return seqids


def local_seqids_filtered(db_dir: Path, *, include_organism: str | None = None,
                          exclude_organism: str | None = None) -> list[str]:
    """Local seqids for an inclusion and/or exclusion organism scope."""
    missing = [name for name in _TAXONOMY_FILES if not (db_dir / name).is_file()]
    if missing:
        raise SearchError(
            f"Local taxonomy files missing in {db_dir}: {', '.join(missing)}. "
            "Stage names.dmp + nodes.dmp (NCBI taxdmp.zip) and the "
            "sprot.taxidmap used at makeblastdb time next to the database.")
    names = parse_names_dmp((db_dir / "names.dmp").read_text(encoding="utf-8"))
    children = parse_nodes_dmp((db_dir / "nodes.dmp").read_text(encoding="utf-8"))
    include = (expand_taxid(resolve_organism_taxid(include_organism, names), children)
               if include_organism else None)
    exclude = (expand_taxid(resolve_organism_taxid(exclude_organism, names), children)
               if exclude_organism else set())
    seqids = select_seqids_filtered(
        (db_dir / "sprot.taxidmap").read_text(encoding="utf-8"), include, exclude)
    if not seqids:
        raise SearchError(
            "No local swissprot sequence matches this organism scope "
            f"(include={include_organism!r}, exclude={exclude_organism!r}).")
    return seqids


def parse_blastdbcmd_fasta(text: str) -> dict:
    """Parse `blastdbcmd -outfmt %f` output into an accession record. Pure."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines or not lines[0].startswith(">"):
        raise SearchError("Local accession lookup returned no FASTA record.")
    import re

    header = lines[0][1:]
    parts = header.split(None, 1)
    fields = parts[0].split("|")
    accession = fields[1] if len(fields) > 1 else parts[0]
    title = parts[1] if len(parts) > 1 else ""
    organism_match = re.search(r"OS=([^=]+?)(?:\s+[A-Z]{2}=|$)", title)
    organism = organism_match.group(1).strip() if organism_match else ""
    bracket = re.search(r"\[([^\]]+)\]\s*$", title)
    if bracket:
        organism = organism or bracket.group(1)
    return {
        "accession": accession,
        "sequence": "".join(lines[1:]).upper(),
        "organism": organism,
        "annotation": title or header,
    }


class LocalBlast:
    """Default backend: BLAST+ binaries against local databases in $BLASTDB
    (swissprot copy plus the NCBI-built databases in _LOCAL_DB_MAP).

    Searches run synchronously in submit(); poll() only reports the
    stored outcome. Fully offline once BLAST+ and $BLASTDB exist.
    """

    name = "local"

    def __init__(self, db_dir: Path | str | None = None) -> None:
        self._db_dir = Path(db_dir) if db_dir else resolve_blast_db_dir()
        self._results: dict[str, list[dict]] = {}
        self._counter = 0

    def _db_path(self, database: str) -> Path:
        if database in _LOCAL_DB_MAP:
            stem = _LOCAL_DB_MAP[database]
        else:
            entry = local_database_entry(database, self._db_dir)
            if entry is None:
                served = sorted(set(_LOCAL_DB_MAP) |
                                {d["name"] for d in load_custom_databases(self._db_dir)})
                raise SearchError(
                    f"LocalBlast does not serve database {database!r} locally "
                    f"(serves: {', '.join(served)}). "
                    "Set SEARCH_BACKEND=ncbi for other databases.")
            stem = entry["stem"]
        if not any(self._db_dir.glob(stem + ".*")):
            raise SearchError(
                f"Local database {database!r} (files {stem}.*) not found in "
                f"{self._db_dir}. Download its FASTA source and build it "
                "with makeblastdb there first, or set SEARCH_BACKEND=ncbi.")
        return self._db_dir / stem

    def fetch_by_accession(self, accession: str) -> dict:
        import shutil
        import subprocess

        from . import config

        if not shutil.which("blastdbcmd"):
            raise SearchError("blastdbcmd not found on PATH. Install NCBI BLAST+.")
        acc = accession.strip().split()[0]
        for stem in _LOCAL_FETCH_STEMS:
            if not any(self._db_dir.glob(stem + ".*")):
                continue
            try:
                proc = subprocess.run(
                    ["blastdbcmd", "-db", str(self._db_dir / stem),
                     "-entry", acc, "-outfmt", "%f"],
                    capture_output=True, text=True,
                    timeout=config.LOCAL_BLAST_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired as exc:
                raise SearchError(f"Local accession lookup timed out for {acc}: {exc}")
            if proc.returncode == 0 and proc.stdout.strip():
                return parse_blastdbcmd_fasta(proc.stdout)
        raise SearchError(
            f"Accession {acc} not found in the local databases "
            f"({', '.join(_LOCAL_FETCH_STEMS)}) in {self._db_dir}.")

    def submit(self, *, sequence: str, program: str, database: str, parameters: dict) -> str:
        import shutil
        import subprocess
        import tempfile

        from . import config

        db_path = self._db_path(database)
        if not shutil.which(program):
            raise SearchError(f"{program} not found on PATH. Install NCBI BLAST+.")
        with tempfile.TemporaryDirectory(prefix="whatsgene_") as tmp:
            query_fasta = Path(tmp) / "query.fasta"
            query_fasta.write_text(f">query\n{sequence}\n", encoding="utf-8")
            seqidlist_path = None
            organism_filter = parameters.get("organism_filter")
            exclude_organism = parameters.get("exclude_organism")
            if (organism_filter or exclude_organism) and db_path.name != "swissprot":
                raise SearchError(
                    f"Organism filtering is only wired for the local swissprot "
                    f"database, not {db_path.name}. Run this search without an "
                    "organism filter, or pick swissprot / the real NCBI backend.")
            if organism_filter or exclude_organism:
                seqids = local_seqids_filtered(
                    self._db_dir,
                    include_organism=str(organism_filter) if organism_filter else None,
                    exclude_organism=str(exclude_organism) if exclude_organism else None)
                seqidlist_path = Path(tmp) / "seqidlist.txt"
                seqidlist_path.write_text("\n".join(seqids) + "\n", encoding="utf-8")
            cmd = build_blast_command(
                program=program, db_path=db_path, query_fasta=query_fasta,
                evalue=parameters.get("evalue_threshold"),
                word_size=parameters.get("word_size"),
                matrix=parameters.get("matrix"),
                seqidlist_path=seqidlist_path)
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True,
                                      timeout=config.LOCAL_BLAST_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired as exc:
                raise SearchError(f"Local {program} run timed out: {exc}")
        if proc.returncode != 0:
            raise SearchError(
                f"Local {program} failed (exit {proc.returncode}): "
                f"{proc.stderr.strip()[-500:]}")
        self._counter += 1
        token = f"LOCAL-{self._counter}"
        self._results[token] = parse_blast_xml(proc.stdout)
        return token

    def poll(self, token: str) -> str:
        return "ready" if token in getattr(self, "_results", {}) else "expired"

    def fetch_results(self, token: str) -> list[dict]:
        try:
            return [dict(h) for h in self._results[token]]
        except KeyError:
            raise SearchError(f"Unknown local search token {token}.")


# --- NcbiRemote pure helpers (unit-tested; no HTTP here) ---

_NCBI_MIN_POLL_SECONDS = 60.0


def ncbi_poll_interval_seconds() -> float:
    """Seconds between NCBI polls — never faster than once per 60s."""
    from . import config

    try:
        configured = float(config.NCBI_POLL_INTERVAL_SECONDS)
    except (TypeError, ValueError):
        configured = _NCBI_MIN_POLL_SECONDS
    return max(configured, _NCBI_MIN_POLL_SECONDS)


def ncbi_max_wait_seconds() -> float:
    """Seconds before an NCBI search aborts (default 30 min)."""
    from . import config

    try:
        return float(config.NCBI_MAX_WAIT_SECONDS)
    except (TypeError, ValueError):
        return 1800.0


def poll_delay_or_abort(*, elapsed: float, rid: str) -> float:
    """Return the next poll delay, or raise SearchError past the wait budget."""
    max_wait = ncbi_max_wait_seconds()
    if elapsed >= max_wait:
        minutes = max_wait / 60.0
        raise SearchError(
            f"NCBI search {rid} did not finish within {minutes:.0f} minutes "
            "and was aborted. The NCBI BLAST queue is slow; try again later "
            "or run locally with SEARCH_BACKEND=local.")
    return ncbi_poll_interval_seconds()


def map_search_status(text: str) -> str:
    """Map a SearchInfo response to ready/failed/expired/waiting. Pure."""
    if "Status=READY" in text:
        return "ready"
    if "Status=FAILED" in text:
        return "failed"
    if "Status=UNKNOWN" in text:
        return "expired"
    return "waiting"


def build_entrez_query(organism_filter: str | None,
                       exclude_organism: str | None = None) -> str | None:
    """Build the NCBI Entrez organism query. Pure.

    Inclusion: "X"[Organism]. Exclusion (Lab 04 Q4 hint):
    NOT "HIV-1"[Organism]. Both combine with NOT.
    """
    parts = []
    if organism_filter:
        parts.append(f'"{organism_filter}"[Organism]')
    query = " ".join(parts) if parts else None
    if exclude_organism:
        exclusion = f'NOT "{exclude_organism}"[Organism]'
        query = f"{query} {exclusion}" if query else exclusion
    return query


class InflightGuard:
    """At most one in-flight NCBI search per backend instance."""

    def __init__(self) -> None:
        self._token: str | None = None

    def check_free(self) -> None:
        if self._token is not None:
            raise SearchError(
                f"NcbiRemote already has an in-flight search ({self._token}); "
                "only one NCBI search runs at a time.")

    def acquire(self, token: str) -> None:
        self.check_free()
        self._token = token

    def release(self) -> None:
        self._token = None


_BLAST_CGI = "https://blast.ncbi.nlm.nih.gov/Blast.cgi"
_DB_MAP = {"refseq_protein": "refseq_protein", "refseq_nucleotide": "nt", "est": "est", "nt": "nt", "nr": "nr"}


def _accession_db(accession: str) -> str:
    acc = accession.upper()
    if acc.startswith(("NM_", "XM_", "NR_", "XR_", "NC_", "NG_", "NT_", "NW_")):
        return "nucleotide"
    return "protein"


class NcbiRemote:
    """Opt-in backend (SEARCH_BACKEND=ncbi): E-utilities + BLAST URL API.

    Sends tool + contact email on every request, keeps at most one
    search in flight, polls no faster than once per 60s, and aborts a
    search that is not done after 30 minutes with a clear error.
    """

    name = "ncbi"

    _submit_lock = __import__('threading').Lock()
    _last_submit_at: float | None = None

    def __init__(self) -> None:
        from . import config

        if not config.NCBI_EMAIL:
            raise SearchError(
                "NCBI_EMAIL is not set. Set it in backend/.env "
                "(NCBI etiquette requires tool + contact email).")
        self._guard = InflightGuard()

    def fetch_by_accession(self, accession: str) -> dict:
        import io
        import os

        try:  # Python's urllib ignores the OS keychain; use certifi's bundle.
            import certifi

            os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        except Exception:
            pass

        from Bio import Entrez, SeqIO

        from . import config

        Entrez.email = config.NCBI_EMAIL
        Entrez.tool = config.NCBI_TOOL
        if config.NCBI_API_KEY:
            Entrez.api_key = config.NCBI_API_KEY
        acc = accession.strip().upper()
        last_error: Exception | None = None
        for db in dict.fromkeys([_accession_db(acc), "protein", "nucleotide"]):
            try:
                with Entrez.efetch(db=db, id=acc, rettype="fasta", retmode="text") as handle:
                    record = SeqIO.read(io.StringIO(handle.read()), "fasta")
                return {
                    "accession": record.id or acc,
                    "sequence": str(record.seq).upper(),
                    "organism": "",
                    "annotation": record.description or "",
                }
            except Exception as exc:  # try the other database, then report
                last_error = exc
        raise SearchError(f"NCBI could not fetch accession {acc}: {last_error}")

    def submit(self, *, sequence: str, program: str, database: str, parameters: dict) -> str:
        import re

        import httpx

        from . import config

        if getattr(self, "_guard", None) is None:
            self._guard = InflightGuard()
        self._guard.check_free()  # refuse before any NCBI request
        import time as _time

        with NcbiRemote._submit_lock:
            wait = ncbi_submit_wait_seconds(
                last_submit_at=NcbiRemote._last_submit_at, now=_time.monotonic())
            if wait:
                _time.sleep(wait)
            NcbiRemote._last_submit_at = _time.monotonic()
        ncbi_db = _DB_MAP.get(database, database)
        data = {
            "CMD": "Put",
            "PROGRAM": program,
            "DATABASE": ncbi_db,
            "QUERY": f">query\n{sequence}",
            "EMAIL": config.NCBI_EMAIL,
            "TOOL": config.NCBI_TOOL,
        }
        entrez = build_entrez_query(parameters.get("organism_filter"),
                                    parameters.get("exclude_organism"))
        if entrez:
            data["ENTREZ_QUERY"] = entrez
        if parameters.get("evalue_threshold") is not None:
            data["EXPECT"] = str(parameters["evalue_threshold"])
        if parameters.get("word_size") is not None:
            data["WORD_SIZE"] = str(parameters["word_size"])
        if parameters.get("matrix"):
            data["MATRIX_NAME"] = str(parameters["matrix"])
        if parameters.get("max_target_sequences") is not None:
            data["NUM_DESCRIPTIONS"] = str(parameters["max_target_sequences"])
            data["NUM_ALIGNMENTS"] = str(parameters["max_target_sequences"])
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(_BLAST_CGI, data=data)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SearchError(f"NCBI BLAST submission failed: {exc}")
        match = re.search(r"RID\s*=\s*([A-Z0-9\-]+)", response.text)
        if not match:
            raise SearchError(
                f"NCBI BLAST submission returned no RID (program {program}, database {ncbi_db}).")
        rid = match.group(1)
        self._guard.acquire(rid)
        return rid

    def poll(self, token: str) -> str:
        import time

        import httpx

        start = time.monotonic()
        try:
            while True:
                try:
                    with httpx.Client(timeout=60.0) as client:
                        response = client.get(_BLAST_CGI, params={
                            "CMD": "Get", "RID": token, "FORMAT_OBJECT": "SearchInfo"})
                        response.raise_for_status()
                    status = map_search_status(response.text)
                except httpx.HTTPError:
                    # Transient network failure: wait out the interval, then retry.
                    time.sleep(poll_delay_or_abort(elapsed=time.monotonic() - start, rid=token))
                    continue
                if status != "waiting":
                    return status
                time.sleep(poll_delay_or_abort(elapsed=time.monotonic() - start, rid=token))
        finally:
            self._guard.release()

    def fetch_results(self, token: str) -> list[dict]:
        import time

        import httpx

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with httpx.Client(timeout=120.0) as client:
                    response = client.get(_BLAST_CGI, params={
                        "CMD": "Get", "RID": token, "FORMAT_TYPE": "XML"})
                    response.raise_for_status()
                return parse_blast_xml(response.text)
            except httpx.HTTPError as exc:  # transient: retry, then fail loudly
                last_error = exc
                time.sleep(15.0 * (attempt + 1))
        raise SearchError(f"NCBI result fetch failed for {token}: {last_error}")


# --- Fixture backend (tests and demo; never touches the network) ---

_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


class Fixture:
    """Recorded-response backend for tests and demos.

    Fixture("globin_nematode") loads tests/fixtures/globin_nematode.json.
    Explicit sequences/primary_hits/reciprocal_hits override file content.
    Searches are distinguished by parameters['kind'] == 'reciprocal'
    plus parameters['candidate_accession'].
    """

    name = "fixture"

    def __init__(self, case: str | None = None, *,
                 sequences: dict[str, dict] | None = None,
                 primary_hits: list[dict] | None = None,
                 reciprocal_hits: dict[str, list[dict]] | None = None) -> None:
        data: dict = {}
        if case:
            stem = case[:-5] if case.endswith(".json") else case
            if not stem or "/" in stem or "\\" in stem or stem.startswith("."):
                raise SearchError(f"Invalid fixture case {case!r}.")
            path = _FIXTURE_DIR / f"{stem}.json"
            if not path.is_file():
                available = sorted(p.stem for p in _FIXTURE_DIR.glob("*.json"))
                raise SearchError(
                    f"Unknown fixture case {stem!r} ({path} not found). "
                    f"Available: {available}.")
            import json

            data = json.loads(path.read_text(encoding="utf-8"))
        self._sequences = sequences if sequences is not None else data.get("sequences", {})
        self._primary = primary_hits if primary_hits is not None else data.get("primary_hits", [])
        self._reciprocal = (reciprocal_hits if reciprocal_hits is not None
                            else data.get("reciprocal_hits", {}))
        self.submissions: list[dict] = []
        self._counter = 0

    def fetch_by_accession(self, accession: str) -> dict:
        try:
            return dict(self._sequences[accession.upper()])
        except KeyError:
            raise SearchError(f"No fixture sequence recorded for {accession}.")

    def submit(self, *, sequence: str, program: str, database: str, parameters: dict) -> str:
        self._counter += 1
        rid = f"FIXTURE-{self._counter}"
        self.submissions.append({
            "rid": rid, "program": program, "database": database,
            "parameters": dict(parameters), "sequence_len": len(sequence),
        })
        return rid

    def poll(self, token: str) -> str:
        return "ready" if any(s["rid"] == token for s in self.submissions) else "expired"

    def fetch_results(self, token: str) -> list[dict]:
        sub = next((s for s in self.submissions if s["rid"] == token), None)
        if sub and sub["parameters"].get("kind") == "reciprocal":
            candidate = sub["parameters"].get("candidate_accession", "")
            return [dict(h) for h in self._reciprocal.get(candidate, [])]
        return [dict(h) for h in self._primary]


_BACKEND_CHOICES = ("server", "local", "ncbi", "fixture")


def normalize_backend_choice(choice: str | None) -> str:
    """Normalise a per-workflow backend choice. Pure."""
    value = (choice or "server").strip().lower()
    if value in ("default", ""):
        value = "server"
    if value not in _BACKEND_CHOICES:
        raise SearchError(
            f"Unknown search backend {choice!r}. Use server, local, ncbi, or fixture.")
    return value


def get_backend_for_choice(choice: str | None) -> SearchBackend:
    """Build the backend for one workflow's choice.

    "server" keeps the configured SEARCH_BACKEND; local/ncbi/fixture
    override it for this workflow only.
    """
    from . import config

    value = normalize_backend_choice(choice)
    if value == "server":
        return get_backend()
    if value == "local":
        return LocalBlast()
    if value == "ncbi":
        return NcbiRemote()
    return Fixture(config.FIXTURE_CASE or None)


def ncbi_submit_wait_seconds(*, last_submit_at: float | None, now: float) -> float:
    """Seconds to wait so NCBI submits are >= 10s apart (charter). Pure."""
    if last_submit_at is None:
        return 0.0
    return max(0.0, 10.0 - (now - last_submit_at))


def get_backend() -> SearchBackend:
    """Build the configured backend. SEARCH_BACKEND=local (default) | ncbi | fixture."""
    from . import config

    choice = (config.SEARCH_BACKEND or "local").strip().lower()
    if choice == "local":
        return LocalBlast()
    if choice == "ncbi":
        return NcbiRemote()
    if choice == "fixture":
        return Fixture(config.FIXTURE_CASE or None)
    raise SearchError(
        f"Unknown SEARCH_BACKEND={choice!r}. Use local, ncbi, or fixture.")
